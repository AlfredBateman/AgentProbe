"""Branch baselines (SPEC.md §8, PLAN.md §2 #2, ADR 0018): the run a branch is compared
against. Set explicitly (e.g. on merge to the trunk branch), never automatically by
`/ci/report`, so one bad PR run can't silently become the new baseline.
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.auth import CurrentPrincipal, Db
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Baseline, Run, Suite
from agentprobe_api.projects import owned_project
from agentprobe_api.runs import RunOut, owned_run

router = APIRouter(tags=["baselines"])


class BaselineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch: str = Field(min_length=1, max_length=200)
    run_id: uuid.UUID


class BaselineOut(BaseModel):
    branch: str
    run_id: uuid.UUID
    suite_id: uuid.UUID
    run: RunOut


async def _load(db: AsyncSession, project_id: uuid.UUID, branch: str) -> BaselineOut | None:
    row = (
        await db.execute(
            select(Baseline, Run)
            .join(Run, Run.id == Baseline.run_id)
            .where(Baseline.project_id == project_id, Baseline.branch == branch)
        )
    ).first()
    if row is None:
        return None
    baseline, run = row
    return BaselineOut(
        branch=baseline.branch, run_id=run.id, suite_id=run.suite_id, run=RunOut.model_validate(run)
    )


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
    stmt = insert(Baseline).values(project_id=project.id, branch=body.branch, run_id=run.id)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["project_id", "branch"], set_={"run_id": stmt.excluded.run_id}
        )
    )
    await db.flush()
    loaded = await _load(db, project.id, body.branch)
    if loaded is None:
        raise ApiError(500, "could not read back the baseline just set", code="internal_error")
    return loaded


@router.get("/projects/{project_id}/baselines/{branch}")
async def get_baseline(
    project_id: uuid.UUID, branch: str, principal: CurrentPrincipal, db: Db
) -> BaselineOut:
    project = await owned_project(db, principal, project_id)
    loaded = await _load(db, project.id, branch)
    if loaded is None:
        raise ApiError(404, f"no baseline set for branch {branch!r}")
    return loaded
