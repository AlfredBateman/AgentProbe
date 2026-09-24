"""Shareable read-only run links (SPEC.md §4.12, ADR 0018): an unguessable token lets
anyone view a sanitized summary of a run without an account. `runs.share_token_hash` stores
only the SHA-256 of the token (ADR 0006/0007); the plaintext token is returned once, at
creation.

The public view is read directly off persisted columns (no `finalize_run` recomputation,
unlike the authenticated export), and never includes agent config, secrets, or any
internal id beyond what the URL already implies. It also leaves out the raw HTTP trace
(tool-call argument JSON, per-message steps) that the authenticated `/results/{id}/trace`
carries — narrower by design.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import runstore
from agentprobe_api.auth import CurrentPrincipal, Db
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Judgment, Run, RunCaseSummary, RunResult, TestCase
from agentprobe_api.runs import owned_run
from agentprobe_api.security import sha256

router = APIRouter(tags=["share"])


class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class ShareOut(BaseModel):
    token: str
    url: str | None
    expires_at: datetime | None


def _share_url(request: Request, token: str) -> str | None:
    base = request.app.state.settings.public_web_url
    return f"{base.rstrip('/')}/shared/{token}" if base else None


@router.post("/runs/{run_id}/share", status_code=201)
async def create_share(
    run_id: uuid.UUID, body: ShareIn, principal: CurrentPrincipal, db: Db, request: Request
) -> ShareOut:
    run = await owned_run(db, principal, run_id)
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    )
    run.share_token_hash = sha256(token)
    run.share_expires_at = expires_at
    await db.flush()
    return ShareOut(token=token, url=_share_url(request, token), expires_at=expires_at)


@router.delete("/runs/{run_id}/share", status_code=204)
async def revoke_share(run_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> None:
    run = await owned_run(db, principal, run_id)
    run.share_token_hash = None
    run.share_expires_at = None


class SharedCaseOut(BaseModel):
    case: str
    label: str
    pass_rate: float
    passes: int
    attempts: int


class SharedJudgmentOut(BaseModel):
    judge: str
    status: str
    reason: str | None


class SharedResultOut(BaseModel):
    case: str
    attempt: int
    status: str
    output: str | None
    score: float | None
    error_kind: str | None
    judgments: list[SharedJudgmentOut]


class SharedRunOut(BaseModel):
    suite: str
    agent: str
    status: str
    runs_per_case: int
    pass_rate: float | None
    ci_lower: float | None
    ci_upper: float | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cases: list[SharedCaseOut]
    results: list[SharedResultOut]


async def _find_shared_run(db: AsyncSession, token: str) -> Run:
    run = await db.scalar(
        select(Run).where(
            Run.share_token_hash == sha256(token),
            (Run.share_expires_at.is_(None)) | (Run.share_expires_at > func.now()),
        )
    )
    if run is None:
        raise ApiError(404, "This share link doesn't exist or has expired")
    return run


async def _shared_cases(db: AsyncSession, run_id: uuid.UUID) -> list[SharedCaseOut]:
    rows = await db.execute(
        select(
            TestCase.case_key,
            RunCaseSummary.label,
            RunCaseSummary.pass_rate,
            RunCaseSummary.passes,
            RunCaseSummary.attempts,
        )
        .join(TestCase, TestCase.id == RunCaseSummary.case_id)
        .where(RunCaseSummary.run_id == run_id)
        .order_by(TestCase.case_key)
    )
    return [
        SharedCaseOut(case=key, label=label, pass_rate=rate, passes=passes, attempts=attempts)
        for key, label, rate, passes, attempts in rows.tuples()
    ]


async def _shared_results(db: AsyncSession, run_id: uuid.UUID) -> list[SharedResultOut]:
    rows = await db.execute(
        select(
            RunResult.id,
            TestCase.case_key,
            RunResult.attempt,
            RunResult.status,
            RunResult.output,
            RunResult.score,
            RunResult.error_kind,
        )
        .join(TestCase, TestCase.id == RunResult.case_id)
        .where(RunResult.run_id == run_id)
        .order_by(TestCase.case_key, RunResult.attempt)
    )
    results = [
        (result_id, case_key, attempt, status, output, score, error_kind)
        for result_id, case_key, attempt, status, output, score, error_kind in rows.tuples()
    ]

    judgments: dict[uuid.UUID, list[SharedJudgmentOut]] = {}
    for run_result_id, judge_type, status, reason in (
        await db.execute(
            select(Judgment.run_result_id, Judgment.judge_type, Judgment.status, Judgment.reason)
            .join(RunResult, RunResult.id == Judgment.run_result_id)
            .where(RunResult.run_id == run_id)
        )
    ).tuples():
        if run_result_id is None:
            continue  # attempt-scope only; never reached given the join above
        judgments.setdefault(run_result_id, []).append(
            SharedJudgmentOut(judge=judge_type, status=status, reason=reason)
        )

    return [
        SharedResultOut(
            case=case_key,
            attempt=attempt,
            status=status,
            output=output,
            score=score,
            error_kind=error_kind,
            judgments=judgments.get(result_id, []),
        )
        for result_id, case_key, attempt, status, output, score, error_kind in results
    ]


@router.get("/shared/{token}")
async def get_shared(token: str, db: Db) -> SharedRunOut:
    run = await _find_shared_run(db, token)
    suite_name = runstore.parsed_suite(run).suite
    agent_name = str(run.config_snapshot.get("agent", {}).get("name", ""))
    return SharedRunOut(
        suite=suite_name,
        agent=agent_name,
        status=run.status,
        runs_per_case=run.runs_per_case,
        pass_rate=run.pass_rate,
        ci_lower=run.ci_lower,
        ci_upper=run.ci_upper,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        cases=await _shared_cases(db, run.id),
        results=await _shared_results(db, run.id),
    )
