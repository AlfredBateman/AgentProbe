"""Baselines (SPEC.md §8, PLAN.md §2 #2, ADRs 0018 and 0020): the run a suite's agent on a
branch is compared against, keyed on (project, suite, branch, agent_id or agent_name). Set
explicitly (e.g. on merge to the trunk branch), never automatically by `/ci/report`, so one
bad PR run can't silently become the new baseline.
"""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import runstore
from agentprobe_api.auth import CurrentPrincipal, Db
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Agent, Baseline, Run, Suite
from agentprobe_api.projects import owned_project
from agentprobe_api.runs import RunOut, owned_run
from agentprobe_core.stats import RegressionReport, compare_runs

router = APIRouter(tags=["baselines"])
KEY = "uq_baselines_project_id_suite_id_branch_agent_id_agent_name"
DEFAULT_BRANCH = "main"  # for runs started without a branch (the dashboard's), ADR 0031


class BaselineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: str = Field(min_length=1, max_length=200)
    run_id: uuid.UUID  # its suite and agent complete the baseline's key


class BaselineOut(BaseModel):
    branch: str
    suite_id: uuid.UUID
    agent_id: uuid.UUID | None
    agent_name: str | None
    run_id: uuid.UUID
    run: RunOut


class RunVerdictOut(BaseModel):
    """A run against its baseline: `report` is core's `RegressionReport`, None when the run
    is the baseline itself or hasn't completed yet.
    """

    branch: str
    baseline_run_id: uuid.UUID
    is_baseline: bool
    report: dict[str, Any] | None


def _out(branch: str, run: Run) -> BaselineOut:
    return BaselineOut(
        branch=branch,
        suite_id=run.suite_id,
        agent_id=run.agent_id,
        agent_name=run.agent_name,
        run_id=run.id,
        run=RunOut.model_validate(run),
    )


async def find_baseline(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    suite_id: uuid.UUID,
    branch: str,
    agent_id: uuid.UUID | None,
    agent_name: str | None,
) -> Baseline | None:
    baseline: Baseline | None = await db.scalar(
        select(Baseline).where(
            Baseline.project_id == project_id,
            Baseline.suite_id == suite_id,
            Baseline.branch == branch,
            Baseline.agent_id.is_not_distinct_from(agent_id),
            Baseline.agent_name.is_not_distinct_from(agent_name),
        )
    )
    return baseline


@router.post("/projects/{project_id}/baseline", status_code=201)
async def set_baseline(
    project_id: uuid.UUID, body: BaselineIn, principal: CurrentPrincipal, db: Db
) -> BaselineOut:
    project = await owned_project(db, principal, project_id)
    run = await owned_run(db, principal, body.run_id)
    suite = await db.get(Suite, run.suite_id)
    if suite is None or suite.project_id != project.id:
        raise ApiError(422, "the run does not belong to a suite in this project")
    if run.status != "completed":
        raise ApiError(422, f"only a completed run can be a baseline (this one is {run.status!r})")
    stmt = insert(Baseline).values(
        project_id=project.id,
        suite_id=run.suite_id,
        branch=body.branch,
        agent_id=run.agent_id,
        agent_name=run.agent_name,
        run_id=run.id,
    )
    await db.execute(stmt.on_conflict_do_update(constraint=KEY, set_={"run_id": run.id}))
    return _out(body.branch, run)


@router.get("/projects/{project_id}/baselines/{branch}")
async def get_baseline(
    project_id: uuid.UUID,
    branch: str,
    principal: CurrentPrincipal,
    db: Db,
    suite: str,
    agent: str | None = None,
    agent_name: str | None = None,
) -> BaselineOut:
    """The baseline of suite `suite` (by name) for a registered `agent` (by name) or an
    unregistered `agent_name` on `branch`.
    """
    project = await owned_project(db, principal, project_id)
    if (agent is None) == (agent_name is None):
        raise ApiError(422, "give exactly one of `agent` (registered) or `agent_name`")
    row = (
        await db.execute(
            select(Baseline, Run)
            .join(Run, Run.id == Baseline.run_id)
            .join(Suite, Suite.id == Baseline.suite_id)
            .outerjoin(Agent, Agent.id == Baseline.agent_id)
            .where(
                Baseline.project_id == project.id,
                Baseline.branch == branch,
                Suite.name == suite,
                Agent.name == agent if agent is not None else Baseline.agent_name == agent_name,
            )
        )
    ).first()
    if row is None:
        raise ApiError(404, f"no baseline set for suite {suite!r} on branch {branch!r}")
    return _out(row[0].branch, row[1])


@router.get("/runs/{run_id}/verdict")
async def run_verdict(run_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> RunVerdictOut:
    """This run against the baseline of its suite and agent on its branch (`main` for a run
    without one). 404 when no baseline is set there.
    """
    run = await owned_run(db, principal, run_id)
    project_id = (
        await db.execute(select(Suite.project_id).where(Suite.id == run.suite_id))
    ).scalar_one()
    branch = run.branch or DEFAULT_BRANCH
    baseline = await find_baseline(
        db,
        project_id,
        suite_id=run.suite_id,
        branch=branch,
        agent_id=run.agent_id,
        agent_name=run.agent_name,
    )
    if baseline is None:
        raise ApiError(404, f"no baseline set for this suite and agent on branch {branch!r}")
    out = RunVerdictOut(
        branch=branch, baseline_run_id=baseline.run_id, is_baseline=False, report=None
    )
    if baseline.run_id == run.id:
        return out.model_copy(update={"is_baseline": True})
    if run.status != "completed":
        return out
    report = compare_runs(
        await runstore.read_case_summaries(db, baseline.run_id),
        await runstore.read_case_summaries(db, run.id),
        runstore.parsed_suite(run).statistics,
    )
    return out.model_copy(
        update={"report": TypeAdapter(RegressionReport).dump_python(report, mode="json")}
    )
