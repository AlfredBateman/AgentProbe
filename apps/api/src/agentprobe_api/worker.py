"""The Redis backend's worker (ADR 0017). Run it with

    taskiq worker agentprobe_api.worker:broker      (or `pnpm dev:worker`)

It needs DATABASE_URL, REDIS_URL and ENCRYPTION_KEY (for agents with an auth header).

Jobs, all idempotent:
- `start_run(run_id)`: claims the run and kicks one `run_attempt` per attempt not saved yet.
- `run_attempt(run_id, case_key, attempt)`: core's `execute_with_retries`, then an upsert
  on (run, case, attempt). The job that saves the last attempt kicks `finalize`.
- `finalize(run_id)`: core's `finalize_run` over the saved attempts.

The broker is a Redis stream with a consumer group, so a job a dead worker took is
redelivered to another one after the idle timeout. On startup the worker also resumes
runs that have been quiet for RUN_STALE_AFTER_S.
"""

import uuid

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker
from taskiq import SmartRetryMiddleware, TaskiqEvents, TaskiqState
from taskiq_redis import RedisStreamBroker

from agentprobe_api import runstore
from agentprobe_api.crypto import SecretBox
from agentprobe_api.db import make_engine
from agentprobe_api.logs import configure_logging
from agentprobe_api.progress import RedisBus
from agentprobe_api.queue import (
    Deps,
    RedisQueue,
    fail_run,
    finalize,
    publish_status,
    record_attempt,
)
from agentprobe_api.runstore import Unrecoverable
from agentprobe_api.settings import get_settings
from agentprobe_core.runner import execute_with_retries, plan_attempts

_settings = get_settings()
broker = RedisStreamBroker(
    url=_settings.redis_url,
    queue_name="agentprobe:jobs",
    consumer_group_name="agentprobe-workers",
    consumer_id="0",  # a new group also reads jobs kicked before it existed
    unacknowledged_lock_timeout=30,  # a crashed worker can't hold the reclaim lock forever
).with_middlewares(
    # For unexpected job failures (e.g. a dropped DB connection). Agent and LLM errors are
    # retried inside core, and a failed attempt is a result, not a job failure.
    SmartRetryMiddleware(
        default_retry_count=3,
        default_retry_label=True,
        default_delay=1,
        use_jitter=True,
        use_delay_exponent=True,
        max_delay_exponent=30,
    )
)
_deps: Deps | None = None


def bind(deps: Deps | None) -> None:
    """The worker's dependencies: set on startup, or by tests running jobs in-process."""
    global _deps
    _deps = deps


def deps() -> Deps:
    if _deps is None:
        raise RuntimeError("the worker has not started (agentprobe_api.worker.bind)")
    return _deps


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _startup(state: TaskiqState) -> None:
    configure_logging(_settings.log_level)
    engine = make_engine(_settings.database_url)
    state.engine = engine
    key = _settings.encryption_key
    bind(
        Deps(
            settings=_settings,
            sessions=async_sessionmaker(engine, expire_on_commit=False),
            secret_box=SecretBox(key) if key else None,
            bus=RedisBus(Redis.from_url(_settings.redis_url)),
        )
    )
    await RedisQueue(deps()).recover()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _shutdown(state: TaskiqState) -> None:
    await deps().bus.aclose()
    await state.engine.dispose()
    bind(None)


@broker.task(task_name="agentprobe.start_run")
async def start_run(run_id: str) -> None:
    d, rid = deps(), uuid.UUID(run_id)
    if not await runstore.claim(d.sessions, rid):
        return
    try:
        plan = await runstore.load_plan(d.sessions, rid, d.secret_box)
        if plan is None:
            return
        await plan.llm()  # fail now, not in every attempt, on a bad LLM config
        await runstore.close_adapter(plan.adapter())
    except Unrecoverable as exc:
        await fail_run(d, rid, str(exc))
        return
    await publish_status(d, rid)
    saved = {(r.case_id, r.attempt) for r in await runstore.load_attempts(d.sessions, rid)}
    missing = [
        (case.id, n)
        for case, n in plan_attempts(plan.suite, plan.runs_per_case)
        if (case.id, n) not in saved
    ]
    for case_key, n in missing:
        await run_attempt.kiq(run_id, case_key, n)
    if not missing:
        await finalize_run.kiq(run_id)


@broker.task(task_name="agentprobe.run_attempt")
async def run_attempt(run_id: str, case_key: str, attempt: int) -> None:
    d, rid = deps(), uuid.UUID(run_id)
    try:
        plan = await runstore.load_plan(d.sessions, rid, d.secret_box)
        if plan is None or plan.status != "running":
            return  # gone, cancelled or failed
        if await runstore.attempt_saved(d.sessions, plan, case_key, attempt):
            return  # a redelivered job: never call the agent twice
        case = plan.case(case_key)
        llm = await plan.llm()
        adapter = plan.adapter()
    except Unrecoverable as exc:
        await fail_run(d, rid, str(exc))
        await finalize_run.kiq(run_id)
        return
    try:
        result = await execute_with_retries(
            case, adapter, llm=llm, options=plan.options(d.settings), attempt=attempt
        )
    finally:
        await runstore.close_adapter(adapter)
    if await record_attempt(d, plan, result) in ("complete", "failed"):
        await finalize_run.kiq(run_id)


@broker.task(task_name="agentprobe.finalize")
async def finalize_run(run_id: str) -> None:
    d, rid = deps(), uuid.UUID(run_id)
    try:
        plan = await runstore.load_plan(d.sessions, rid, d.secret_box)
    except Unrecoverable as exc:
        await fail_run(d, rid, str(exc))
        return
    if plan is not None:
        await finalize(d, plan)
