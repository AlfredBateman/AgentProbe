"""The Redis worker's job edges, offline: a run that can't be rebuilt, a run that's gone, a
resumed run with nothing left to do, and the worker's startup and shutdown hooks.
test_runs_redis.py runs the happy paths through real Redis in CI.
"""

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agentprobe_api import worker
from agentprobe_api.runstore import Unrecoverable
from agentprobe_core.suite import parse_suite_yaml
from apitest import make_settings

RUN = str(uuid.uuid4())
SUITE = parse_suite_yaml("""
suite: s
agent: a
runs_per_case: 2
cases:
  - id: only
    input: hi
    expect:
      - judge: contains
        value: hi
""")


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    """The worker bound to fakes; `kicked` records the jobs it enqueues."""
    spies = SimpleNamespace(
        fail_run=AsyncMock(),
        publish_status=AsyncMock(),
        finalize=AsyncMock(),
        run_attempt=AsyncMock(),
        finalize_run=AsyncMock(),
    )
    for name in ("fail_run", "publish_status", "finalize"):
        monkeypatch.setattr(worker, name, getattr(spies, name))
    monkeypatch.setattr(worker.runstore, "claim", AsyncMock(return_value=True))
    monkeypatch.setattr(worker.runstore, "close_adapter", AsyncMock())
    # The jobs kick each other through these task objects' .kiq.
    monkeypatch.setattr(worker.run_attempt, "kiq", spies.run_attempt)
    monkeypatch.setattr(worker.finalize_run, "kiq", spies.finalize_run)
    worker.bind(SimpleNamespace(sessions=None, secret_box=None, settings=make_settings()))  # type: ignore[arg-type]
    yield spies
    worker.bind(None)


def load_plan(monkeypatch: pytest.MonkeyPatch, result: Any) -> None:
    mock = (
        AsyncMock(side_effect=result)
        if isinstance(result, Exception)
        else AsyncMock(return_value=result)
    )
    monkeypatch.setattr(worker.runstore, "load_plan", mock)


def test_jobs_refuse_to_run_before_the_worker_starts() -> None:
    worker.bind(None)
    with pytest.raises(RuntimeError, match="has not started"):
        worker.deps()


async def test_start_run_fails_a_run_it_cant_rebuild(
    jobs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    load_plan(monkeypatch, Unrecoverable("snapshot is unreadable"))
    await worker.start_run.original_func(RUN)
    jobs.fail_run.assert_awaited_once()
    assert jobs.fail_run.await_args.args[2] == "snapshot is unreadable"
    jobs.run_attempt.assert_not_awaited()
    jobs.publish_status.assert_not_awaited()


async def test_start_run_does_nothing_for_a_run_that_is_gone(
    jobs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    load_plan(monkeypatch, None)
    await worker.start_run.original_func(RUN)
    jobs.publish_status.assert_not_awaited()
    jobs.run_attempt.assert_not_awaited()
    jobs.fail_run.assert_not_awaited()


async def test_start_run_on_a_fully_saved_run_only_finalizes(
    jobs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run resumed after every attempt was saved, but before it was finalized."""
    plan = SimpleNamespace(suite=SUITE, runs_per_case=2, llm=AsyncMock(), adapter=lambda: object())
    load_plan(monkeypatch, plan)
    saved = [SimpleNamespace(case_id="only", attempt=n) for n in (0, 1)]
    monkeypatch.setattr(worker.runstore, "load_attempts", AsyncMock(return_value=saved))
    await worker.start_run.original_func(RUN)
    jobs.run_attempt.assert_not_awaited()
    jobs.finalize_run.assert_awaited_once_with(RUN)


async def test_run_attempt_fails_the_run_and_finalizes_when_it_cant_rebuild(
    jobs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    load_plan(monkeypatch, Unrecoverable("agent config no longer validates"))
    await worker.run_attempt.original_func(RUN, "only", 0)
    jobs.fail_run.assert_awaited_once()
    jobs.finalize_run.assert_awaited_once_with(RUN)


async def test_finalize_fails_a_run_it_cant_rebuild_without_summarizing(
    jobs: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    load_plan(monkeypatch, Unrecoverable("suite no longer parses"))
    await worker.finalize_run.original_func(RUN)
    jobs.fail_run.assert_awaited_once()
    jobs.finalize.assert_not_awaited()


async def test_startup_binds_the_workers_dependencies_and_resumes_runs_shutdown_unbinds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    bus = SimpleNamespace(aclose=AsyncMock())
    recover = AsyncMock()
    monkeypatch.setattr(worker, "make_engine", lambda url: engine)
    monkeypatch.setattr(worker, "RedisBus", lambda redis: bus)
    monkeypatch.setattr(worker, "RedisQueue", lambda deps: SimpleNamespace(recover=recover))
    state = SimpleNamespace()

    await worker._startup(state)  # type: ignore[arg-type]
    assert worker.deps().bus is bus
    recover.assert_awaited_once()

    await worker._shutdown(state)  # type: ignore[arg-type]
    bus.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    with pytest.raises(RuntimeError):
        worker.deps()
