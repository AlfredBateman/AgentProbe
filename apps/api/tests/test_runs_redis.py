"""The same run scenarios on the Redis backend: Taskiq jobs on a Redis stream, executed by
the real worker jobs in-process (so they share the test's rolled-back transaction), with
progress over Redis pub/sub. CI only: marked `redis`.

Also proves the two backends agree: the same suite and seed give identical attempt results
and summaries inline and on Redis.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq.api import run_receiver_task

from agentprobe_api import runstore, worker
from agentprobe_api.main import create_app
from agentprobe_api.models import Judgment, Run, RunCaseSummary, RunResult, TestCase
from agentprobe_api.progress import channel
from agentprobe_api.queue import RedisQueue
from agentprobe_core.adapters.types import AgentAdapter, AgentResponse
from agentprobe_demo_agents import flaky
from apitest import SignUp, bind_db, client_for, make_settings
from runtest import (
    SMOKE_YAML,
    NullQueue,
    deps_of,
    make_project,
    normalized,
    parse_sse,
    start_run,
    wait_for_run,
)

pytestmark = [pytest.mark.integration, pytest.mark.redis, pytest.mark.usefixtures("demo_env")]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
StartWorker = Callable[[], Awaitable[None]]


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL)
    await client.flushdb()  # CI's own Redis: no jobs or groups left over from other tests
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def app(db: AsyncSession, redis: Redis) -> AsyncIterator[FastAPI]:
    settings = make_settings(
        queue_backend="redis", redis_url=REDIS_URL, run_max_retries=1, run_backoff_base_s=0.01
    )
    app = bind_db(create_app(settings), db)
    worker.bind(deps_of(app))  # what the worker's startup hook does in production
    await app.state.queue.start()  # declares the consumer group
    yield app
    worker.broker.is_worker_process = False  # run_receiver_task sets it; don't fire worker hooks
    await app.state.queue.aclose()
    await app.state.bus.aclose()
    worker.bind(None)


@pytest.fixture
async def start_worker() -> AsyncIterator[StartWorker]:
    """Starts the worker (in-process) when the test says so."""
    tasks: list[asyncio.Task[None]] = []

    async def start() -> None:
        tasks.append(asyncio.create_task(run_receiver_task(worker.broker, max_async_tasks=8)))

    yield start
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def drained(redis: Redis) -> None:
    """Waits until every job kicked so far has been read and acknowledged."""
    async with asyncio.timeout(60):
        while True:
            groups = await redis.xinfo_groups("agentprobe:jobs")
            if groups and all(g["pending"] == 0 and g["lag"] == 0 for g in groups):
                return
            await asyncio.sleep(0.2)


async def count(db: AsyncSession, model: Any, *where: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def test_a_run_completes_through_the_worker(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str, start_worker: StartWorker
) -> None:
    await start_worker()
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    assert (done["status"], done["attempts_done"], done["error"]) == ("completed", 4, None)
    assert done["pass_rate"] == 1.0
    run_id = uuid.UUID(run["id"])
    assert await count(db, RunResult, RunResult.run_id == run_id) == 4
    assert await count(db, RunCaseSummary, RunCaseSummary.run_id == run_id) == 2
    assert await count(db, Judgment, Judgment.run_id == run_id) == 1  # case-scope consistency


async def test_sse_streams_over_redis_pubsub(
    sign_up: SignUp, app: FastAPI, redis: Redis, demo_url: str, start_worker: StartWorker
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    run = await start_run(alice, ids["suite_id"])  # no worker yet: it waits in the stream
    run_id = uuid.UUID(run["id"])
    stream = asyncio.create_task(alice.get(f"/runs/{run_id}/stream"))
    async with asyncio.timeout(10):
        while not (await redis.pubsub_numsub(channel(run_id)))[0][1]:  # noqa: ASYNC110
            await asyncio.sleep(0.05)
    await start_worker()
    response = await asyncio.wait_for(stream, 60)
    events = parse_sse(response.text)
    assert events[0]["type"] == "snapshot"
    assert sorted(e["done"] for e in events if e["type"] == "attempt") == [1, 2, 3, 4]
    assert [e["status"] for e in events if e["type"] == "status"][-1] == "completed"


async def test_cancel_before_the_worker_picks_it_up(
    sign_up: SignUp,
    app: FastAPI,
    redis: Redis,
    db: AsyncSession,
    demo_url: str,
    start_worker: StartWorker,
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    run = await start_run(alice, ids["suite_id"])
    assert (await alice.post(f"/runs/{run['id']}/cancel")).json()["status"] == "cancelled"
    await start_worker()
    await drained(redis)
    done = (await alice.get(f"/runs/{run['id']}")).json()
    assert (done["status"], done["attempts_done"], done["started_at"]) == ("cancelled", 0, None)
    assert await count(db, RunResult, RunResult.run_id == uuid.UUID(run["id"])) == 0


async def test_an_unreachable_agent_fails_the_run(
    sign_up: SignUp, app: FastAPI, redis: Redis, db: AsyncSession, start_worker: StartWorker
) -> None:
    await start_worker()
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMOKE_YAML, max_retries=0)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    await drained(redis)
    assert done["status"] == "failed"
    assert done["error"].startswith("unreachable error: could not connect")
    rows = (
        await db.scalars(select(RunResult).where(RunResult.run_id == uuid.UUID(run["id"])))
    ).all()
    assert 1 <= len(rows) < 40  # jobs that started after the failure saw it and stopped
    assert {(r.error_kind, r.retries) for r in rows} == {("unreachable", 1)}


async def test_a_redelivered_attempt_job_never_calls_the_agent_twice(
    sign_up: SignUp,
    app: FastAPI,
    db: AsyncSession,
    demo_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    app.state.queue = NullQueue()
    run = await start_run(alice, ids["suite_id"])
    assert await runstore.claim(deps_of(app).sessions, uuid.UUID(run["id"]))
    calls: list[str] = []
    real_adapter = runstore.Plan.adapter

    class Counting:
        def __init__(self, inner: AgentAdapter) -> None:
            self.inner = inner

        async def invoke(self, input: str, context: Any = ()) -> AgentResponse:
            calls.append(input)
            return await self.inner.invoke(input, context)

        async def aclose(self) -> None:
            await runstore.close_adapter(self.inner)

    monkeypatch.setattr(runstore.Plan, "adapter", lambda plan: Counting(real_adapter(plan)))
    for _ in range(2):  # the same job, delivered twice
        await worker.run_attempt(run["id"], "greeting", 0)
    assert calls == ["Hello there"]
    assert await count(db, RunResult, RunResult.run_id == uuid.UUID(run["id"])) == 1


async def test_the_startup_sweep_resumes_stale_runs(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str, start_worker: StartWorker
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    queue, app.state.queue = app.state.queue, NullQueue()  # its job is lost with a dead Redis
    stale = await start_run(alice, ids["suite_id"])
    fresh = await start_run(alice, ids["suite_id"])
    app.state.queue = queue
    await db.execute(
        update(Run)
        .where(Run.id == uuid.UUID(stale["id"]))
        .values(created_at=func.now() - timedelta(hours=1))
    )
    await db.commit()
    assert isinstance(queue, RedisQueue)
    await queue.recover()  # what the worker runs at startup
    await start_worker()
    assert (await wait_for_run(alice, app, stale["id"]))["status"] == "completed"
    assert (await alice.get(f"/runs/{fresh['id']}")).json()["status"] == "queued"


async def summaries(db: AsyncSession, run_id: uuid.UUID) -> dict[str, Any]:
    run = await db.get(Run, run_id, populate_existing=True)
    assert run is not None
    rows = await db.execute(
        select(
            TestCase.case_key,
            RunCaseSummary.attempts,
            RunCaseSummary.passes,
            RunCaseSummary.errors,
            RunCaseSummary.pass_rate,
            RunCaseSummary.label,
            RunCaseSummary.mean_score,
            RunCaseSummary.consistency_score,
        )
        .join(TestCase, TestCase.id == RunCaseSummary.case_id)
        .where(RunCaseSummary.run_id == run_id)
    )
    return {
        "run": (
            run.status,
            run.attempts_done,
            run.pass_rate,
            run.ci_lower,
            run.ci_upper,
            run.total_tokens,
        ),
        "cases": sorted(tuple(row) for row in rows.tuples()),
    }


async def test_both_backends_give_identical_results_and_summaries(
    sign_up: SignUp,
    app: FastAPI,
    redis: Redis,
    db: AsyncSession,
    demo_url: str,
    start_worker: StartWorker,
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    await start_worker()
    flaky.reset()  # the same seed for both runs
    on_redis = await start_run(alice, ids["suite_id"], runs_per_case=3)
    assert (await wait_for_run(alice, app, on_redis["id"]))["status"] == "completed"
    await drained(redis)

    inline_app = bind_db(create_app(make_settings(run_backoff_base_s=0.01)), db)
    inline_alice = client_for(inline_app, cookies=alice.cookies)
    flaky.reset()
    inline = await start_run(inline_alice, ids["suite_id"], runs_per_case=3)
    assert (await wait_for_run(inline_alice, inline_app, inline["id"]))["status"] == "completed"
    await inline_alice.aclose()

    sessions = deps_of(app).sessions
    redis_id, inline_id = uuid.UUID(on_redis["id"]), uuid.UUID(inline["id"])
    redis_results = await runstore.load_attempts(sessions, redis_id)
    inline_results = await runstore.load_attempts(sessions, inline_id)
    assert len(redis_results) == len(inline_results) == 24
    assert normalized(redis_results) == normalized(inline_results)
    assert await summaries(db, redis_id) == await summaries(db, inline_id)
