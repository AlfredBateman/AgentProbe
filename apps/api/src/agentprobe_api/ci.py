"""`POST /ci/report` (SPEC.md §8, PLAN.md §2 #2, ADRs 0018-0020): the CLI/GitHub Action
upload a run it already executed (the agent is often only reachable from the user's own
CI), the server persists it and compares it with the baseline for the same suite, branch
and agent. It is the only run-ingest endpoint (ADR 0019), and it returns structured data
only: the Action formats its PR comment from this JSON.

The suite must already exist in the project (`POST /projects/{id}/suites`), looked up by
name. The agent is either a registered one (`agent`, looked up by name, exactly like `POST
/suites/{id}/runs`) or, for agents the server can't hold or run such as the CLI's python
adapter, just a name (`agent_name`, ADR 0020).

Unlike a live run, this is one request doing one piece of work end to end (no queue, no
SSE, nothing to resume if it's interrupted), so it's persisted in the request's own
transaction via `runstore.insert_results` / `insert_summary` rather than the
`Sessions`-based `save_attempt` / `save_summary` a live run uses: those open their own
sessions per call for the queue/worker's benefit, which would deadlock against the same
request's own `db` session here. The row-level field mapping is still shared (ADR 0018).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from sqlalchemy import select

from agentprobe_api import runstore
from agentprobe_api.auth import CurrentApiKey, Db
from agentprobe_api.baselines import find_baseline
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Agent, Run, Suite
from agentprobe_api.projects import owned_project
from agentprobe_core.runner import AttemptResult, check_results, finalize_run
from agentprobe_core.stats import RegressionReport, compare_runs
from agentprobe_core.suite import SuiteParseError, parse_suite_yaml

router = APIRouter(tags=["ci"])
MAX_RESULTS = 500 * 20  # a run's own limit (SPEC's suite MAX_CASES x MAX_RUNS_PER_CASE)


class CiReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite: str = Field(min_length=1, max_length=200)  # matches an existing suite's name
    # Exactly one: a registered agent's name, or the name of an unregistered one (ADR 0020).
    agent: str | None = Field(default=None, min_length=1, max_length=200)
    agent_name: str | None = Field(default=None, min_length=1, max_length=200)
    results: list[AttemptResult] = Field(min_length=1, max_length=MAX_RESULTS)
    runs_per_case: int | None = Field(default=None, ge=1, le=20)
    mock: bool = True
    model: str | None = Field(default=None, max_length=200)  # a label for the agent's model
    git_sha: str | None = Field(default=None, max_length=64)
    branch: str = Field(min_length=1, max_length=200)
    pr_number: int | None = Field(default=None, ge=1)
    # Which branch's Baseline to diff against; defaults to `branch` itself, so CI on the
    # trunk branch compares against its own last recorded baseline. A PR passes this
    # explicitly (e.g. "main") since a feature branch normally has no baseline of its own.
    baseline_branch: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _one_agent(self) -> "CiReportIn":
        if (self.agent is None) == (self.agent_name is None):
            raise ValueError("give exactly one of `agent` (registered) or `agent_name`")
        return self


class CiReportOut(BaseModel):
    run_id: uuid.UUID
    verdict: str  # a stats.Verdict, or "no_baseline" when the target branch has none
    comparison: dict[str, Any] | None
    top_findings: list[Any] = []  # populated once failure clustering exists (Prompt 15)
    dashboard_url: str | None


@router.post("/ci/report", status_code=201)
async def ci_report(
    body: CiReportIn, principal: CurrentApiKey, db: Db, request: Request
) -> CiReportOut:
    if principal.project_id is None:
        raise ApiError(403, "This action requires a project API key, not a user session")
    project = await owned_project(db, principal, principal.project_id)

    suite = await db.scalar(
        select(Suite).where(Suite.project_id == project.id, Suite.name == body.suite)
    )
    if suite is None:
        raise ApiError(422, f"no suite named {body.suite!r} in this project")
    try:
        parsed = parse_suite_yaml(suite.yaml_source)
    except SuiteParseError as exc:
        raise ApiError(422, "the suite's stored YAML no longer parses", details=exc.issues) from exc

    name = body.agent or body.agent_name
    agent = await db.scalar(select(Agent).where(Agent.project_id == project.id, Agent.name == name))
    if body.agent is not None and agent is None:
        raise ApiError(422, f"no agent named {body.agent!r} in this project")
    if body.agent_name is not None and agent is not None:
        # One agent, one identity: otherwise its runs would split across two baselines.
        raise ApiError(422, f"{body.agent_name!r} is a registered agent; send it as `agent`")

    runs_per_case = body.runs_per_case or parsed.runs_per_case
    try:
        check_results(parsed, runs_per_case, body.results)
    except ValueError as exc:
        raise ApiError(422, str(exc)) from exc

    now = datetime.now(UTC)
    run = Run(
        suite_id=suite.id,
        suite_version=suite.version,
        agent_id=agent.id if agent else None,
        agent_name=body.agent_name,
        status="running",
        started_at=now,
        runs_per_case=runs_per_case,
        mock_mode=body.mock,
        model=body.model,
        git_sha=body.git_sha,
        branch=body.branch,
        pr_number=body.pr_number,
        config_snapshot=runstore.make_snapshot(
            suite, agent or str(body.agent_name), runs_per_case=runs_per_case, mock=body.mock
        ),
        attempts_total=len(body.results),
        attempts_done=len(body.results),
    )
    db.add(run)
    await db.flush()

    case_ids = await runstore.case_ids_for(db, suite.id, suite.version)
    await runstore.insert_results(db, run.id, case_ids, body.results)
    saved = await runstore.read_attempts(db, run.id)
    summary = await finalize_run(
        saved,
        suite=parsed,
        agent=name,
        runs_per_case=runs_per_case,
        statistics=parsed.statistics,
        started_at=now,
    )
    await runstore.insert_summary(db, run, case_ids, summary)

    verdict = "no_baseline"
    comparison: dict[str, Any] | None = None
    baseline = await find_baseline(
        db,
        project.id,
        suite_id=suite.id,
        branch=body.baseline_branch or body.branch,
        agent_id=run.agent_id,
        agent_name=run.agent_name,
    )
    if baseline is not None:
        baseline_summaries = await runstore.read_case_summaries(db, baseline.run_id)
        candidate_summaries = summary.case_summaries()
        report = compare_runs(baseline_summaries, candidate_summaries, parsed.statistics)
        verdict = report.verdict
        comparison = TypeAdapter(RegressionReport).dump_python(report, mode="json")

    settings = request.app.state.settings
    dashboard_url = (
        f"{settings.public_web_url.rstrip('/')}/runs/{run.id}" if settings.public_web_url else None
    )
    return CiReportOut(
        run_id=run.id, verdict=verdict, comparison=comparison, dashboard_url=dashboard_url
    )
