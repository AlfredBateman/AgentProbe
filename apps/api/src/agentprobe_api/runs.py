"""Runs (SPEC.md §8, ADR 0017): start a suite run, read it, cancel it, and stream its
progress over Server-Sent Events, with the stream-token fallback of ADR 0009 §5.

Starting a run stores a config snapshot (suite YAML, agent config, secret id) and hands
the run to the queue backend; how it executes is core's `agentprobe_core.runner`.
"""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import runstore
from agentprobe_api.auth import (
    STREAM_TOKEN_TTL,
    AppSettings,
    CurrentPrincipal,
    CurrentUser,
    Db,
    Principal,
    get_principal,
    mint_stream_token,
    stream_principal,
)
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Agent, Project, Run, Suite
from agentprobe_api.progress import Subscription
from agentprobe_api.runstore import LIVE, TERMINAL
from agentprobe_api.suites import owned_suite
from agentprobe_core.runner import plan_attempts
from agentprobe_core.suite import SuiteParseError, parse_suite_yaml

router = APIRouter(tags=["runs"])
HEARTBEAT_S = 15.0  # an SSE comment this often keeps proxies from closing an idle stream


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runs_per_case: int | None = Field(default=None, ge=1, le=20)  # default: the suite's
    model: str | None = Field(default=None, max_length=200)  # a label for the agent's model
    mock: bool = True  # mock LLM for judges; false uses the server's LLM_PROVIDER


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    suite_id: uuid.UUID
    suite_version: int
    agent_id: uuid.UUID
    status: str
    model: str | None
    runs_per_case: int
    mock_mode: bool
    attempts_total: int
    attempts_done: int
    pass_rate: float | None
    ci_lower: float | None
    ci_upper: float | None
    total_tokens: int | None
    total_cost: float | None
    judge_cost_usd: float | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StreamTokenOut(BaseModel):
    token: str
    expires_in: int


async def owned_run(db: AsyncSession, principal: Principal, run_id: uuid.UUID) -> Run:
    """Not-owned and nonexistent are both 404 (mirrors `owned_suite`)."""
    row = (
        await db.execute(
            select(Run, Suite.project_id)
            .join(Suite, Suite.id == Run.suite_id)
            .join(Project, Project.id == Suite.project_id)
            .where(Run.id == run_id, Project.user_id == principal.user_id)
            .execution_options(populate_existing=True)
        )
    ).first()
    if row is None or (principal.project_id is not None and row[1] != principal.project_id):
        raise ApiError(404, "Run not found")
    run: Run = row[0]
    return run


@router.post("/suites/{suite_id}/runs", status_code=202)
async def start_run(
    suite_id: uuid.UUID, body: RunIn, principal: CurrentPrincipal, db: Db, request: Request
) -> RunOut:
    suite = await owned_suite(db, principal, suite_id)
    try:
        parsed = parse_suite_yaml(suite.yaml_source)
    except SuiteParseError as exc:  # stored YAML was valid when uploaded; limits may change
        raise ApiError(422, "Suite validation failed", details=exc.issues) from exc
    agent = await db.scalar(
        select(Agent).where(Agent.project_id == suite.project_id, Agent.name == parsed.agent)
    )
    if agent is None:
        raise ApiError(422, f"The suite's agent {parsed.agent!r} isn't in this project")
    if agent.adapter_type != "http":
        raise ApiError(422, f"{agent.adapter_type} agents can't run on the server yet")
    runs_per_case = body.runs_per_case or parsed.runs_per_case
    try:
        attempts = plan_attempts(parsed, runs_per_case)
    except ValueError as exc:
        raise ApiError(422, str(exc)) from exc
    run = Run(
        suite_id=suite.id,
        suite_version=suite.version,
        agent_id=agent.id,
        status="queued",
        model=body.model,
        runs_per_case=runs_per_case,
        mock_mode=body.mock,
        config_snapshot=runstore.make_snapshot(
            suite, agent, runs_per_case=runs_per_case, mock=body.mock
        ),
        attempts_total=len(attempts),
    )
    db.add(run)
    await db.flush()
    out = RunOut.model_validate(run)
    await db.commit()  # the queue runs it in another session: it must be visible first
    await request.app.state.queue.enqueue(run.id)
    return out


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> RunOut:
    return RunOut.model_validate(await owned_run(db, principal, run_id))


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: uuid.UUID, principal: CurrentPrincipal, db: Db, request: Request
) -> RunOut:
    run = await owned_run(db, principal, run_id)
    changed = await db.scalar(
        update(Run)
        .where(Run.id == run.id, Run.status.in_(LIVE))
        .values(status="cancelled", finished_at=func.now())
        .returning(Run.id)
    )
    if changed is None:
        raise ApiError(409, f"The run has already ended ({run.status})")
    await db.commit()
    await db.refresh(run)
    await request.app.state.queue.cancel(run.id)
    await request.app.state.bus.publish(run.id, runstore.run_event(run))
    return RunOut.model_validate(run)


@router.post("/runs/{run_id}/stream-token")
async def stream_token(
    run_id: uuid.UUID, principal: CurrentUser, db: Db, settings: AppSettings
) -> StreamTokenOut:
    run = await owned_run(db, principal, run_id)
    return StreamTokenOut(
        token=mint_stream_token(settings, principal.user_id, run.id),
        expires_in=int(STREAM_TOKEN_TTL.total_seconds()),
    )


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: uuid.UUID,
    request: Request,
    db: Db,
    settings: AppSettings,
    token: str | None = None,
) -> StreamingResponse:
    """`snapshot` (the run's state now), then `attempt` and `status` events until the run
    ends. Authenticated like any request, or with `?token=` from `POST
    /runs/{id}/stream-token` where the browser can't send the session cookie.
    """
    principal = (
        stream_principal(settings, token, run_id)
        if token is not None
        else await get_principal(request, db, settings)
    )
    await owned_run(db, principal, run_id)
    stack = AsyncExitStack()
    # Subscribe before reading the snapshot, so no event falls between the two.
    subscription = await stack.enter_async_context(request.app.state.bus.subscribe(run_id))
    try:
        run = await owned_run(db, principal, run_id)
        snapshot = runstore.run_event(run, "snapshot")
    except BaseException:
        await stack.aclose()
        raise
    return StreamingResponse(
        _events(snapshot, subscription, stack),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


async def _events(
    snapshot: dict[str, Any], subscription: Subscription, stack: AsyncExitStack
) -> AsyncIterator[str]:
    try:
        yield _sse(snapshot)
        if snapshot["status"] in TERMINAL:
            return
        while True:
            event = await subscription.next(HEARTBEAT_S)
            if event is None:
                yield ": keep-alive\n\n"
                continue
            yield _sse(event)
            if event["type"] == "status" and event["status"] in TERMINAL:
                return
    finally:
        await stack.aclose()
