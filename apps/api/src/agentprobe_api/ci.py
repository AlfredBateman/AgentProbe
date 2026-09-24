"""`POST /ci/report` (SPEC.md §8, PLAN.md §2 #2, ADR 0018): the CLI/GitHub Action upload a
run it already executed (the agent is often only reachable from the user's own CI), the
server persists it and compares it with a branch's baseline.

The suite and agent must already exist in the project (`POST /projects/{id}/suites` /
`POST /projects/{id}/agents`), looked up by name, exactly like `POST /suites/{id}/runs`.

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
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select

from agentprobe_api import runstore
from agentprobe_api.auth import CurrentApiKey, Db
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Agent, Baseline, Run, Suite
from agentprobe_api.projects import owned_project
from agentprobe_core.runner import AttemptResult, finalize_run, plan_attempts
from agentprobe_core.stats import RegressionReport, compare_runs
from agentprobe_core.suite import SuiteParseError, parse_suite_yaml

router = APIRouter(tags=["ci"])
MAX_RESULTS = 500 * 20  # a run's own limit (SPEC's suite MAX_CASES x MAX_RUNS_PER_CASE)


class CiReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite: str = Field(min_length=1, max_length=200)  # matches an existing suite's name
    agent: str = Field(min_length=1, max_length=200)  # matches an existing agent's name
    results: list[AttemptResult] = Field(min_length=1, max_length=MAX_RESULTS)
    runs_per_case: int | None = Field(default=None, ge=1, le=20)
    mock: bool = True
    git_sha: str | None = Field(default=None, max_length=64)
    branch: str = Field(min_length=1, max_length=200)
    pr_number: int | None = Field(default=None, ge=1)
    # Which branch's Baseline to diff against; defaults to `branch` itself, so CI on the
    # trunk branch compares against its own last recorded baseline. A PR passes this
    # explicitly (e.g. "main") since a feature branch normally has no baseline of its own.
    baseline_branch: str | None = Field(default=None, max_length=200)


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

    agent = await db.scalar(
        select(Agent).where(Agent.project_id == project.id, Agent.name == body.agent)
    )
    if agent is None:
        raise ApiError(422, f"no agent named {body.agent!r} in this project")

    runs_per_case = body.runs_per_case or parsed.runs_per_case
    try:
        expected = plan_attempts(parsed, runs_per_case)
    except ValueError as exc:
        raise ApiError(422, str(exc)) from exc
    if len(body.results) > len(expected):
        raise ApiError(
            422,
            f"{len(body.results)} results for {len(expected)} expected attempts "
            f"({len(parsed.cases)} cases x {runs_per_case} runs)",
        )
    case_keys = {c.id for c in parsed.cases}
    seen: set[tuple[str, int]] = set()
    for result in body.results:
        if result.case_id not in case_keys:
            raise ApiError(422, f"unknown case id {result.case_id!r} in results")
        key = (result.case_id, result.attempt)
        if key in seen:
            raise ApiError(
                422, f"duplicate result for case {result.case_id!r} attempt {result.attempt}"
            )
        seen.add(key)

    now = datetime.now(UTC)
    run = Run(
        suite_id=suite.id,
        suite_version=suite.version,
        agent_id=agent.id,
        status="running",
        started_at=now,
        runs_per_case=runs_per_case,
        mock_mode=body.mock,
        git_sha=body.git_sha,
        branch=body.branch,
        pr_number=body.pr_number,
        config_snapshot=runstore.make_snapshot(
            suite, agent, runs_per_case=runs_per_case, mock=body.mock
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
        agent=agent.name,
        runs_per_case=runs_per_case,
        statistics=parsed.statistics,
        started_at=now,
    )
    await runstore.insert_summary(db, run, case_ids, summary)

    baseline_branch = body.baseline_branch or body.branch
    verdict = "no_baseline"
    comparison: dict[str, Any] | None = None
    baseline_run_id = await db.scalar(
        select(Baseline.run_id).where(
            Baseline.project_id == project.id, Baseline.branch == baseline_branch
        )
    )
    if baseline_run_id is not None:
        baseline_summaries = await runstore.read_case_summaries(db, baseline_run_id)
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
