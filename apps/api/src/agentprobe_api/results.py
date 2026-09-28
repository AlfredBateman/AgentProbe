"""Per-attempt results, one attempt's full trace, and the regression diff between two runs
(SPEC.md §8, ADR 0018). The diff itself is core's `agentprobe_core.stats.compare_runs`;
nothing here reimplements it.
"""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import runstore
from agentprobe_api.auth import CurrentPrincipal, Db, Principal
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Judgment, Project, Run, RunCaseSummary, RunResult, Suite, TestCase
from agentprobe_api.runs import owned_run
from agentprobe_core.adapters.types import TraceStep
from agentprobe_core.runner import judgment_steps
from agentprobe_core.stats import RegressionReport, compare_runs

router = APIRouter(tags=["results"])


class JudgmentOut(BaseModel):
    judge: str
    status: str
    score: float | None
    reason: str | None


class ResultOut(BaseModel):
    id: uuid.UUID
    case: str
    attempt: int
    status: str
    label: str | None  # the case's overall label in this run; None until it's summarized
    attack_category: str | None
    output: str | None
    latency_ms: int | None
    tokens: int | None
    cost: float | None
    error_kind: str | None
    score: float | None
    judgments: list[JudgmentOut]


class TraceJudgmentOut(JudgmentOut):
    step: int | None  # index into `steps` of the step it concerns; None: the whole attempt


class TraceOut(BaseModel):
    run_id: uuid.UUID
    case: str
    attempt: int
    status: str
    input: str
    output: str | None
    error: str | None
    latency_ms: float | None
    tokens: int | None
    cost_usd: float | None
    judge_cost_usd: float
    retries: int
    steps: list[TraceStep]
    judgments: list[TraceJudgmentOut]


class CaseSummaryOut(BaseModel):
    case: str
    attack_category: str | None
    label: str
    attempts: int
    passes: int
    errors: int
    pass_rate: float
    mean_score: float | None
    consistency_score: float | None
    mean_latency_ms: float | None
    total_cost: float | None


class CompareOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_run_id: uuid.UUID
    candidate_run_id: uuid.UUID
    report: dict[str, Any]


async def owned_result(
    db: AsyncSession, principal: Principal, result_id: uuid.UUID
) -> tuple[RunResult, Run]:
    """Not-owned and nonexistent are both 404 (mirrors `owned_run`)."""
    row = (
        await db.execute(
            select(RunResult, Run, Suite.project_id)
            .join(Run, Run.id == RunResult.run_id)
            .join(Suite, Suite.id == Run.suite_id)
            .join(Project, Project.id == Suite.project_id)
            .where(RunResult.id == result_id, Project.user_id == principal.user_id)
        )
    ).first()
    if row is None or (principal.project_id is not None and row[2] != principal.project_id):
        raise ApiError(404, "Result not found")
    return row[0], row[1]


@router.get("/runs/{run_id}/results")
async def list_results(
    run_id: uuid.UUID,
    principal: CurrentPrincipal,
    db: Db,
    status: str | None = None,
    label: str | None = None,
    case: str | None = None,
    attack_category: str | None = None,
) -> list[ResultOut]:
    run = await owned_run(db, principal, run_id)
    query = (
        select(RunResult, TestCase.case_key, TestCase.attack_type, RunCaseSummary.label)
        .join(TestCase, TestCase.id == RunResult.case_id)
        .outerjoin(
            RunCaseSummary,
            (RunCaseSummary.run_id == RunResult.run_id)
            & (RunCaseSummary.case_id == RunResult.case_id),
        )
        .where(RunResult.run_id == run.id)
        .order_by(TestCase.case_key, RunResult.attempt)
    )
    if status is not None:
        query = query.where(RunResult.status == status)
    if label is not None:
        query = query.where(RunCaseSummary.label == label)
    if case is not None:
        query = query.where(TestCase.case_key == case)
    if attack_category is not None:
        query = query.where(TestCase.attack_type == attack_category)
    rows = (await db.execute(query)).all()

    result_ids = [row[0].id for row in rows]
    judgments: dict[uuid.UUID, list[JudgmentOut]] = {rid: [] for rid in result_ids}
    if result_ids:
        for j in await db.scalars(
            select(Judgment)
            .where(Judgment.run_result_id.in_(result_ids))
            .order_by(Judgment.judge_type)
        ):
            if j.run_result_id is None:
                continue  # case-scope judgments aren't in this query; never reached
            judgments[j.run_result_id].append(
                JudgmentOut(judge=j.judge_type, status=j.status, score=j.score, reason=j.reason)
            )

    return [
        ResultOut(
            id=r.id,
            case=case_key,
            attempt=r.attempt,
            status=r.status,
            label=case_label,
            attack_category=attack_type,
            output=r.output,
            latency_ms=r.latency_ms,
            tokens=r.tokens,
            cost=float(r.cost) if r.cost is not None else None,
            error_kind=r.error_kind,
            score=r.score,
            judgments=judgments[r.id],
        )
        for r, case_key, attack_type, case_label in rows
    ]


@router.get("/results/{result_id}/trace")
async def get_trace(result_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> TraceOut:
    _, run = await owned_result(db, principal, result_id)
    attempt = await runstore.read_attempt(db, result_id)
    if attempt is None:
        raise ApiError(404, "Result not found")
    case = next((c for c in runstore.parsed_suite(run).cases if c.id == attempt.case_id), None)
    steps = judgment_steps(case, attempt) if case else [None] * len(attempt.judgments)
    return TraceOut(
        run_id=run.id,
        case=attempt.case_id,
        attempt=attempt.attempt,
        status=attempt.status,
        input=attempt.input,
        output=attempt.response.output if attempt.response else None,
        error=attempt.error.message if attempt.error else None,
        latency_ms=attempt.latency_ms,
        tokens=attempt.tokens,
        cost_usd=attempt.cost_usd,
        judge_cost_usd=attempt.judge_cost_usd,
        retries=attempt.retries,
        steps=attempt.response.steps if attempt.response else [],
        judgments=[
            TraceJudgmentOut(
                judge=j.judge, status=j.status, score=j.score, reason=j.reason, step=step
            )
            for j, step in zip(attempt.judgments, steps, strict=True)
        ],
    )


@router.get("/runs/{run_id}/cases")
async def list_cases(
    run_id: uuid.UUID, principal: CurrentPrincipal, db: Db
) -> list[CaseSummaryOut]:
    """Per-case summaries (label, pass counts, consistency, latency, cost). Written when the
    run is summarized, so empty while it is still running.
    """
    run = await owned_run(db, principal, run_id)
    rows = await db.execute(
        select(RunCaseSummary, TestCase.case_key, TestCase.attack_type)
        .join(TestCase, TestCase.id == RunCaseSummary.case_id)
        .where(RunCaseSummary.run_id == run.id)
        .order_by(TestCase.case_key)
    )
    return [
        CaseSummaryOut(
            case=case_key,
            attack_category=attack_type,
            label=row.label,
            attempts=row.attempts,
            passes=row.passes,
            errors=row.errors,
            pass_rate=row.pass_rate,
            mean_score=row.mean_score,
            consistency_score=row.consistency_score,
            mean_latency_ms=row.mean_latency_ms,
            total_cost=float(row.total_cost) if row.total_cost is not None else None,
        )
        for row, case_key, attack_type in rows.tuples()
    ]


@router.get("/runs/compare")
async def compare(a: uuid.UUID, b: uuid.UUID, principal: CurrentPrincipal, db: Db) -> CompareOut:
    baseline_run = await owned_run(db, principal, a)
    candidate_run = await owned_run(db, principal, b)
    if baseline_run.suite_id != candidate_run.suite_id:
        raise ApiError(422, "the two runs are not of the same suite")
    baseline = await runstore.read_case_summaries(db, baseline_run.id)
    candidate = await runstore.read_case_summaries(db, candidate_run.id)
    config = runstore.parsed_suite(candidate_run).statistics
    report = compare_runs(baseline, candidate, config)
    return CompareOut(
        baseline_run_id=a,
        candidate_run_id=b,
        report=TypeAdapter(RegressionReport).dump_python(report, mode="json"),
    )
