"""Persistence around core's runner (ADR 0017): the config snapshot a run executes from,
idempotent attempt and summary writes, and rebuilding `AttemptResult`s from the database.
Both queue backends use this module; how a run executes stays in `agentprobe_core.runner`.
"""

import json
import os
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import fmean
from typing import Any

from cryptography.fernet import InvalidToken
from pydantic import SecretStr
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.crypto import SecretBox
from agentprobe_api.models import (
    Agent,
    Judgment,
    Run,
    RunCaseSummary,
    RunResult,
    Secret,
    Suite,
    TestCase,
    Trace,
)
from agentprobe_api.settings import Settings
from agentprobe_core.adapters import AdapterNotAllowed, TargetPolicy, build_adapter
from agentprobe_core.adapters.types import AgentAdapter
from agentprobe_core.llm import LLMConfig, LLMConfigError, create_client
from agentprobe_core.llm.types import LLMClient
from agentprobe_core.runner import (
    AttemptResult,
    CaseResult,
    RunOptions,
    RunSummary,
    finalize_run,
    uses_llm,
)
from agentprobe_core.stats.summary import CaseSummary
from agentprobe_core.suite import Case, SuiteParseError, parse_suite_yaml
from agentprobe_core.suite import Suite as SuiteSchema

# `async with sessions() as session`: an async_sessionmaker in production; tests swap in
# one that shares the test's transaction.
Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]
LIVE = ("queued", "running")
TERMINAL = frozenset({"completed", "failed", "cancelled"})


class Unrecoverable(Exception):
    """The run can't be rebuilt from its config snapshot, so it is marked failed."""


def make_snapshot(
    suite: Suite, agent: Agent | str, *, runs_per_case: int, mock: bool
) -> dict[str, Any]:
    """What a run executes, fixed when it starts: editing the suite or agent later doesn't
    change it. It holds the auth header's secret id, never the secret. A `str` agent is an
    unregistered one (ADR 0020): only its name is known.
    """
    return {
        "suite": {"id": str(suite.id), "version": suite.version, "yaml": suite.yaml_source},
        "agent": {"id": None, "name": agent, "adapter_type": None, "config": None}
        if isinstance(agent, str)
        else {
            "id": str(agent.id),
            "name": agent.name,
            "adapter_type": agent.adapter_type,
            "config": agent.config,
            "secret_ref": str(agent.secret_ref) if agent.secret_ref else None,
        },
        "runs_per_case": runs_per_case,
        "mock": mock,
    }


@dataclass(frozen=True)
class Plan:
    """A run rebuilt from its snapshot: everything executing it needs."""

    run_id: uuid.UUID
    status: str
    attempts_total: int
    suite: SuiteSchema
    case_ids: dict[str, uuid.UUID]  # case key -> test_cases.id
    runs_per_case: int
    mock: bool
    agent_name: str
    agent_type: str
    agent_config: dict[str, Any]
    secret_headers: dict[str, SecretStr]

    def case(self, key: str) -> Case:
        for case_ in self.suite.cases:
            if case_.id == key:
                return case_
        raise Unrecoverable(f"case {key!r} is not in the run's suite")

    def options(self, settings: Settings) -> RunOptions:
        return RunOptions(
            runs_per_case=self.runs_per_case,
            concurrency=settings.run_concurrency,
            max_retries=settings.run_max_retries,
            backoff_base_s=settings.run_backoff_base_s,
            statistics=self.suite.statistics,
        )

    def adapter(self) -> AgentAdapter:
        try:
            return build_adapter(
                self.agent_type,
                self.agent_config,
                secret_headers=self.secret_headers,
                policy=TargetPolicy.from_env(),
            )
        except (AdapterNotAllowed, ValueError) as exc:  # ValueError: pydantic validation
            raise Unrecoverable(f"agent config: {exc}") from None

    async def llm(self) -> LLMClient | None:
        """The judges' LLM client, or None when no judge uses one. `mock` forces the mock
        provider; otherwise LLM_PROVIDER decides, and live still needs RUN_LIVE=1.
        """
        if not uses_llm(self.suite):
            return None
        env = dict(os.environ)
        if self.mock:
            env["LLM_PROVIDER"] = "mock"
        try:
            # verify=False: one embedding call per job otherwise. The budget guard is per
            # client, so per job on the Redis backend (ADR 0017, known issue).
            return await create_client(LLMConfig.from_env(env), verify=False)
        except LLMConfigError as exc:
            raise Unrecoverable(f"LLM provider: {exc}") from None


async def close_adapter(adapter: AgentAdapter) -> None:
    close = getattr(adapter, "aclose", None)
    if close is not None:
        await close()


async def case_ids_for(
    session: AsyncSession, suite_id: uuid.UUID, suite_version: int
) -> dict[str, uuid.UUID]:
    """One suite version's case ids, keyed by case key (`test_cases.case_key`)."""
    rows = await session.execute(
        select(TestCase.case_key, TestCase.id).where(
            TestCase.suite_id == suite_id, TestCase.suite_version == suite_version
        )
    )
    # dict(rows.tuples()) is broken: SQLAlchemy's Result exposes .keys(), so the dict
    # constructor treats it as a mapping (column names) instead of iterating (key, value)
    # pairs. A comprehension avoids that trap.
    return {key: id_ for key, id_ in rows.tuples()}


async def load_plan(
    sessions: Sessions, run_id: uuid.UUID, secret_box: SecretBox | None
) -> Plan | None:
    """None if the run doesn't exist (a job for a deleted run). Raises `Unrecoverable`."""
    async with sessions() as session:
        run = await session.get(Run, run_id, populate_existing=True)
        if run is None:
            return None
        status, total, snapshot = run.status, run.attempts_total, run.config_snapshot
        case_ids = await case_ids_for(session, run.suite_id, run.suite_version)
        secret_ref = snapshot.get("agent", {}).get("secret_ref")
        ciphertext = (
            await session.scalar(
                select(Secret.ciphertext).where(Secret.id == uuid.UUID(secret_ref))
            )
            if secret_ref
            else None
        )
    try:
        suite = parse_suite_yaml(snapshot["suite"]["yaml"])
        agent = snapshot["agent"]
        headers: dict[str, SecretStr] = {}
        if secret_ref:
            if ciphertext is None or secret_box is None:
                raise Unrecoverable("the agent's auth header is gone or can't be decrypted")
            header = json.loads(secret_box.decrypt(ciphertext).get_secret_value())
            headers = {header["name"]: SecretStr(header["value"])}
        if missing := [c.id for c in suite.cases if c.id not in case_ids]:
            raise Unrecoverable(f"cases {missing} have no test_cases rows")
        return Plan(
            run_id=run_id,
            status=status,
            attempts_total=total,
            suite=suite,
            case_ids=case_ids,
            runs_per_case=int(snapshot["runs_per_case"]),
            mock=bool(snapshot["mock"]),
            agent_name=str(agent["name"]),
            agent_type=str(agent["adapter_type"]),
            agent_config=dict(agent["config"]),
            secret_headers=headers,
        )
    except (SuiteParseError, KeyError, TypeError, ValueError, InvalidToken) as exc:
        # The type only: the message could quote the decrypted header.
        raise Unrecoverable(
            f"can't rebuild the run from its snapshot ({type(exc).__name__})"
        ) from None


def _money(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, 6)))


async def claim(sessions: Sessions, run_id: uuid.UUID) -> bool:
    """Marks a queued (or resumed) run running. False if it is finished or gone."""
    async with sessions() as session:
        claimed = await session.scalar(
            update(Run)
            .where(Run.id == run_id, Run.status.in_(LIVE))
            .values(
                status="running",
                started_at=func.coalesce(Run.started_at, func.now()),
                heartbeat_at=func.now(),
            )
            .returning(Run.id)
        )
        await session.commit()
    return claimed is not None


async def finish(
    sessions: Sessions, run_id: uuid.UUID, status: str, error: str | None = None
) -> bool:
    """Moves a queued/running run to `failed` or `cancelled`. False if it had already ended."""
    async with sessions() as session:
        changed = await session.scalar(
            update(Run)
            .where(Run.id == run_id, Run.status.in_(LIVE))
            .values(status=status, error=error, finished_at=func.now())
            .returning(Run.id)
        )
        await session.commit()
    return changed is not None


async def attempt_saved(sessions: Sessions, plan: Plan, case_key: str, attempt: int) -> bool:
    async with sessions() as session:
        found = await session.scalar(
            select(RunResult.id).where(
                RunResult.run_id == plan.run_id,
                RunResult.case_id == plan.case_ids[case_key],
                RunResult.attempt == attempt,
            )
        )
    return found is not None


def _attempt_values(run_id: uuid.UUID, case_id: uuid.UUID, result: AttemptResult) -> dict[str, Any]:
    """The `run_results` column values for one attempt. Shared by `save_attempt` (one
    attempt at a time, idempotent, for a live/queued run) and `insert_results` (every
    attempt of an ingested run in one transaction), so the two insert paths can't drift.
    """
    return {
        "id": uuid.uuid4(),
        "run_id": run_id,
        "case_id": case_id,
        "attempt": result.attempt,
        "status": result.status,
        "output": result.response.output if result.response else None,
        "latency_ms": None if result.latency_ms is None else round(result.latency_ms),
        "tokens": result.tokens,
        "cost": _money(result.cost_usd),
        "error_kind": result.error.kind if result.error else None,
        "score": result.score,
        "judge_cost_usd": _money(result.judge_cost_usd),
        "retries": result.retries,
        "detail": result.model_dump(mode="json", exclude={"response": {"steps"}}),
    }


def _judgment_rows(*, run_result_id: uuid.UUID, judgments: list[Any]) -> list[Judgment]:
    return [
        Judgment(
            run_result_id=run_result_id,
            judge_type=j.judge,
            status=j.status,
            passed=j.status == "pass",
            score=j.score,
            reason=j.reason,
            evidence=j.evidence,
        )
        for j in judgments
    ]


async def save_attempt(sessions: Sessions, plan: Plan, result: AttemptResult) -> int | None:
    """Saves one attempt with its trace and judgments, but only while the run is running:
    late results of a cancelled or failed run are dropped. Idempotent on (run, case,
    attempt). Returns the run's `attempts_done` after this one, or None if nothing was saved.
    """
    async with sessions() as session:
        # The row lock orders this against cancel/fail and the other attempts' counter.
        status = await session.scalar(
            select(Run.status).where(Run.id == plan.run_id).with_for_update()
        )
        if status != "running":
            await session.commit()
            return None
        result_id = await session.scalar(
            insert(RunResult)
            .values(**_attempt_values(plan.run_id, plan.case_ids[result.case_id], result))
            .on_conflict_do_nothing(index_elements=["run_id", "case_id", "attempt"])
            .returning(RunResult.id)
        )
        if result_id is None:  # a redelivered job: already saved
            await session.commit()
            return None
        if result.response is not None:
            session.add(
                Trace(
                    run_result_id=result_id,
                    steps=[step.model_dump(mode="json") for step in result.response.steps],
                )
            )
        session.add_all(_judgment_rows(run_result_id=result_id, judgments=result.judgments))
        await session.flush()
        done = await session.scalar(
            update(Run)
            .where(Run.id == plan.run_id)
            .values(attempts_done=Run.attempts_done + 1, heartbeat_at=func.now())
            .returning(Run.attempts_done)
        )
        await session.commit()
    return done


async def insert_results(
    db: AsyncSession,
    run_id: uuid.UUID,
    case_ids: dict[str, uuid.UUID],
    results: list[AttemptResult],
) -> None:
    """Every attempt of an ingested run (`/ci/report`, ADR 0018), in the caller's own
    transaction: one shot, not idempotent-per-call like `save_attempt` (a live run's
    concurrent, resumable writes). Field mapping is shared via `_attempt_values` so the two
    paths can't drift; case ids and (case, attempt) duplicates are the caller's job to
    validate first, so a mistake here is a clear IntegrityError, not a silent skip.
    """
    for result in results:
        row = RunResult(**_attempt_values(run_id, case_ids[result.case_id], result))
        db.add(row)
        await db.flush()  # assigns row.id for the trace/judgments below
        if result.response is not None:
            db.add(
                Trace(
                    run_result_id=row.id,
                    steps=[step.model_dump(mode="json") for step in result.response.steps],
                )
            )
        db.add_all(_judgment_rows(run_result_id=row.id, judgments=result.judgments))
    await db.flush()


def _attempt_result(detail: dict[str, Any], steps: list[dict[str, Any]] | None) -> AttemptResult:
    """Rebuilds one `AttemptResult` from its `run_results.detail` (everything but the trace
    steps) and its `traces.steps`, exactly as core produced it.
    """
    data = dict(detail)
    if data.get("response") is not None:
        data["response"] = {**data["response"], "steps": steps or []}
    return AttemptResult.model_validate(data)


async def load_attempts(sessions: Sessions, run_id: uuid.UUID) -> list[AttemptResult]:
    """`read_attempts` for background work (the queue/worker), which opens its own session."""
    async with sessions() as session:
        return await read_attempts(session, run_id)


async def read_attempts(db: AsyncSession, run_id: uuid.UUID) -> list[AttemptResult]:
    """Every saved attempt of a run, for a request handler's own session (no commit)."""
    rows = await db.execute(
        select(RunResult.detail, Trace.steps)
        .outerjoin(Trace, Trace.run_result_id == RunResult.id)
        .where(RunResult.run_id == run_id)
    )
    return [_attempt_result(detail, steps) for detail, steps in rows.tuples()]


async def read_attempt(db: AsyncSession, result_id: uuid.UUID) -> AttemptResult | None:
    """One saved attempt by its `run_results.id`, or None if it doesn't exist."""
    row = (
        await db.execute(
            select(RunResult.detail, Trace.steps)
            .outerjoin(Trace, Trace.run_result_id == RunResult.id)
            .where(RunResult.id == result_id)
        )
    ).first()
    return None if row is None else _attempt_result(row.detail, row.steps)


async def read_case_summaries(db: AsyncSession, run_id: uuid.UUID) -> dict[str, CaseSummary]:
    """A run's persisted per-case summaries, keyed by case id, for `stats.compare_runs`."""
    rows = await db.execute(
        select(
            TestCase.case_key,
            RunCaseSummary.passes,
            RunCaseSummary.attempts,
            RunCaseSummary.errors,
            RunCaseSummary.mean_score,
            RunCaseSummary.mean_latency_ms,
            RunCaseSummary.total_cost,
        )
        .join(TestCase, TestCase.id == RunCaseSummary.case_id)
        .where(RunCaseSummary.run_id == run_id)
    )
    return {
        key: CaseSummary(
            passes=passes,
            attempts=attempts,
            errors=errors,
            mean_score=mean_score,
            mean_latency_ms=mean_latency_ms,
            cost_usd=float(total_cost) if total_cost is not None else None,
        )
        for key, passes, attempts, errors, mean_score, mean_latency_ms, total_cost in rows.tuples()
    }


def parsed_suite(run: Run) -> SuiteSchema:
    """The `Suite` schema a run executed from: parsed from its own config snapshot, so it
    reflects the suite exactly as it was when the run started, not its current version.
    """
    return parse_suite_yaml(run.config_snapshot["suite"]["yaml"])


async def read_summary(db: AsyncSession, run: Run) -> RunSummary:
    """A `RunSummary` rebuilt from the persisted attempts via core's own `finalize_run`,
    the strongest guarantee that an export agrees with core's statistics. `RunSummary.status`
    only distinguishes completed/cancelled; callers needing the run's real status (queued,
    running, failed, ...) read it off the `Run` row itself.
    """
    suite = parsed_suite(run)
    results = await read_attempts(db, run.id)
    agent_name = run.config_snapshot.get("agent", {}).get("name") or suite.agent
    return await finalize_run(
        results,
        suite=suite,
        agent=agent_name,
        runs_per_case=run.runs_per_case,
        statistics=suite.statistics,
        status="completed" if run.status == "completed" else "cancelled",
        started_at=run.started_at,
        run_id=str(run.id),
    )


def _case_summary_values(run_id: uuid.UUID, case_id: uuid.UUID, c: CaseResult) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "case_id": case_id,
        "attempts": c.summary.attempts,
        "passes": c.summary.passes,
        "errors": c.summary.errors,
        "pass_rate": c.pass_rate,
        "label": c.label,
        "mean_score": c.summary.mean_score,
        "consistency_score": fmean(j.score for j in c.consistency) if c.consistency else None,
        "mean_latency_ms": c.summary.mean_latency_ms,
        "total_cost": _money(c.summary.cost_usd),
    }


def _case_judgment_rows(
    run_id: uuid.UUID, case_ids: dict[str, uuid.UUID], cases: list[CaseResult]
) -> list[Judgment]:
    return [
        Judgment(
            run_id=run_id,
            case_id=case_ids[c.case_id],
            judge_type=j.judge,
            status=j.status,
            passed=j.status == "pass",
            score=j.score,
            reason=j.reason,
            evidence=j.evidence,
        )
        for c in cases
        for j in c.consistency
    ]


async def save_summary(sessions: Sessions, plan: Plan, summary: RunSummary) -> str:
    """Saves per-case summaries, case-scope consistency judgments and the run's totals, and
    completes a running run (a cancelled or failed one keeps its status). Idempotent.
    Returns the run's status.
    """
    async with sessions() as session:
        if summary.cases:
            rows = [
                _case_summary_values(plan.run_id, plan.case_ids[c.case_id], c)
                for c in summary.cases
            ]
            stmt = insert(RunCaseSummary).values(rows)
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["run_id", "case_id"],
                    set_={k: stmt.excluded[k] for k in rows[0] if k not in ("run_id", "case_id")},
                )
            )
        await session.execute(delete(Judgment).where(Judgment.run_id == plan.run_id))
        session.add_all(_case_judgment_rows(plan.run_id, plan.case_ids, summary.cases))
        await session.flush()
        status = await session.scalar(
            update(Run)
            .where(Run.id == plan.run_id)
            .values(
                status=case((Run.status.in_(LIVE), "completed"), else_=Run.status),
                finished_at=func.coalesce(Run.finished_at, func.now()),
                pass_rate=summary.pass_rate,
                ci_lower=summary.ci.lower if summary.ci else None,
                ci_upper=summary.ci.upper if summary.ci else None,
                total_tokens=summary.tokens,
                total_cost=_money(summary.agent_cost_usd),
                judge_cost_usd=_money(summary.judge_cost_usd),
            )
            .returning(Run.status)
        )
        await session.commit()
    return str(status)


async def insert_summary(
    db: AsyncSession, run: Run, case_ids: dict[str, uuid.UUID], summary: RunSummary
) -> None:
    """The ingest counterpart to `save_summary`: writes case summaries, case-scope
    judgments and the run's totals in the caller's own transaction (ADR 0018). A fresh
    ingested run has no pre-existing rows to upsert over or replace.
    """
    db.add_all(
        RunCaseSummary(**_case_summary_values(run.id, case_ids[c.case_id], c))
        for c in summary.cases
    )
    db.add_all(_case_judgment_rows(run.id, case_ids, summary.cases))
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    run.pass_rate = summary.pass_rate
    run.ci_lower = summary.ci.lower if summary.ci else None
    run.ci_upper = summary.ci.upper if summary.ci else None
    run.total_tokens = summary.tokens
    run.total_cost = _money(summary.agent_cost_usd)
    run.judge_cost_usd = _money(summary.judge_cost_usd)
    await db.flush()


async def stale_runs(sessions: Sessions, older_than_s: float | None) -> list[uuid.UUID]:
    """Queued/running runs quiet for `older_than_s` seconds (None: all of them), oldest first."""
    query = select(Run.id).where(Run.status.in_(LIVE)).order_by(Run.created_at)
    if older_than_s is not None:
        last_seen = func.coalesce(Run.heartbeat_at, Run.created_at)
        query = query.where(last_seen < func.now() - timedelta(seconds=older_than_s))
    async with sessions() as session:
        return list((await session.scalars(query)).all())


def run_event(run: Run, kind: str = "status") -> dict[str, Any]:
    """The run's state as a progress event (ids, status and counts only)."""
    return {
        "type": kind,
        "status": run.status,
        "done": run.attempts_done,
        "total": run.attempts_total,
        "pass_rate": run.pass_rate,
        "error": run.error,
    }


async def status_event(sessions: Sessions, run_id: uuid.UUID) -> dict[str, Any] | None:
    async with sessions() as session:
        run = await session.get(Run, run_id, populate_existing=True)
        return None if run is None else run_event(run)
