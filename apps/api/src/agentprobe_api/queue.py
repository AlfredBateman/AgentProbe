"""Queue backends (ADR 0017) behind one `QueueBackend` protocol, selected by QUEUE_BACKEND:

- `inline`: the API process runs a whole run through core's `run_suite`, at most
  INLINE_MAX_RUNS runs at once. Local development and `pnpm verify`.
- `redis`: Taskiq jobs on Redis, one per (run, case, attempt) plus a final one, executed
  by `agentprobe_api.worker`. The jobs call core's `execute_with_retries` and
  `finalize_run`.

Neither reimplements run logic: that lives in `agentprobe_core.runner` (PLAN.md Q6). This
module adds persistence, progress events and the shared run policy:

- the first attempt with an infrastructure error (agent unreachable, LLM budget used up)
  fails the run and stops the rest, as the CLI does;
- a run that was queued or running when its process died is resumed, skipping the
  attempts it already saved; one that can't be rebuilt is marked failed.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

from agentprobe_api import runstore
from agentprobe_api.crypto import SecretBox
from agentprobe_api.progress import ProgressBus
from agentprobe_api.runstore import Plan, Sessions, Unrecoverable
from agentprobe_api.settings import Settings
from agentprobe_core.runner import INFRA_ERRORS, AttemptResult, finalize_run, run_suite

log = logging.getLogger("agentprobe.runs")


@dataclass(frozen=True)
class Deps:
    settings: Settings
    sessions: Sessions
    secret_box: SecretBox | None
    bus: ProgressBus


class QueueBackend(Protocol):
    async def start(self) -> None: ...

    async def enqueue(self, run_id: uuid.UUID) -> None: ...

    async def cancel(self, run_id: uuid.UUID) -> None:
        """Called after the run is marked cancelled: stop executing it and summarize it."""
        ...

    async def recover(self) -> None:
        """Resume the runs a dead process left queued or running."""
        ...

    async def aclose(self) -> None: ...


# --- shared by both backends ----------------------------------------------------------


async def publish_status(deps: Deps, run_id: uuid.UUID) -> None:
    if (event := await runstore.status_event(deps.sessions, run_id)) is not None:
        await deps.bus.publish(run_id, event)


async def fail_run(deps: Deps, run_id: uuid.UUID, message: str) -> None:
    if await runstore.finish(deps.sessions, run_id, "failed", message):
        log.warning("run failed", extra={"run_id": str(run_id), "reason": message})
    await publish_status(deps, run_id)


Outcome = Literal["dropped", "saved", "complete", "failed"]


async def record_attempt(deps: Deps, plan: Plan, result: AttemptResult) -> Outcome:
    """Saves an attempt and publishes it. `complete`: every attempt is now saved.
    `failed`: this attempt's infrastructure error failed the run. `dropped`: already saved,
    or the run isn't running any more.
    """
    done = await runstore.save_attempt(deps.sessions, plan, result)
    if done is None:
        return "dropped"
    await deps.bus.publish(
        plan.run_id,
        {
            "type": "attempt",
            "case": result.case_id,
            "attempt": result.attempt,
            "status": result.status,
            "done": done,
            "total": plan.attempts_total,
        },
    )
    if result.error is not None and result.error.kind in INFRA_ERRORS:
        await fail_run(deps, plan.run_id, f"{result.error.kind} error: {result.error.message}")
        return "failed"
    return "complete" if done >= plan.attempts_total else "saved"


async def finalize(deps: Deps, plan: Plan) -> None:
    """Summarizes the saved attempts with core's `finalize_run`. Idempotent."""
    results = await runstore.load_attempts(deps.sessions, plan.run_id)
    try:
        llm = await plan.llm()
    except Unrecoverable:  # the consistency judge then compares text only
        llm = None
    summary = await finalize_run(
        results,
        suite=plan.suite,
        agent=plan.agent_name,
        runs_per_case=plan.runs_per_case,
        llm=llm,
        statistics=plan.suite.statistics,
    )
    await runstore.save_summary(deps.sessions, plan, summary)
    await publish_status(deps, plan.run_id)


# --- inline -------------------------------------------------------------------------------


async def execute_inline(deps: Deps, run_id: uuid.UUID, cancel: asyncio.Event) -> None:
    """One whole run through core's `run_suite`, resuming from saved attempts."""
    if not await runstore.claim(deps.sessions, run_id):
        return  # finished (e.g. cancelled while queued) or gone
    try:
        plan = await runstore.load_plan(deps.sessions, run_id, deps.secret_box)
        if plan is None:
            return
        llm = await plan.llm()
        adapter = plan.adapter()
    except Unrecoverable as exc:
        await fail_run(deps, run_id, str(exc))
        return
    await publish_status(deps, run_id)

    async def on_result(result: AttemptResult) -> None:
        if await record_attempt(deps, plan, result) == "failed":
            cancel.set()

    try:
        summary = await run_suite(
            plan.suite,
            adapter,
            llm=llm,
            options=plan.options(deps.settings),
            agent=plan.agent_name,
            on_result=on_result,
            cancel=cancel,
            completed=await runstore.load_attempts(deps.sessions, run_id),
        )
    finally:
        await runstore.close_adapter(adapter)
    if summary.status == "completed":
        await runstore.save_summary(deps.sessions, plan, summary)
        await publish_status(deps, run_id)
    else:  # cancelled or failed: summarize exactly what was saved
        await finalize(deps, plan)


class InlineQueue:
    def __init__(self, deps: Deps) -> None:
        self._deps = deps
        self._slots = asyncio.Semaphore(deps.settings.inline_max_runs)
        self._cancels: dict[uuid.UUID, asyncio.Event] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        pass

    async def enqueue(self, run_id: uuid.UUID) -> None:
        cancel = self._cancels.setdefault(run_id, asyncio.Event())
        task = asyncio.create_task(self._run(run_id, cancel), name=f"run-{run_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, run_id: uuid.UUID, cancel: asyncio.Event) -> None:
        try:
            async with self._slots:
                await execute_inline(self._deps, run_id, cancel)
        except Exception:
            log.exception("run crashed", extra={"run_id": str(run_id)})
            await fail_run(self._deps, run_id, "internal error")
        finally:
            self._cancels.pop(run_id, None)

    async def cancel(self, run_id: uuid.UUID) -> None:
        if (event := self._cancels.get(run_id)) is not None:
            event.set()

    async def recover(self) -> None:
        # Only this process runs inline runs, so at startup every live one is orphaned.
        # ponytail: one API process only; with several, use the redis backend.
        for run_id in await runstore.stale_runs(self._deps.sessions, None):
            await self.enqueue(run_id)

    async def join(self) -> None:
        """Waits for every run in flight (tests)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


# --- redis ----------------------------------------------------------------------------------


class RedisQueue:
    """Kicks the worker's jobs (`agentprobe_api.worker`, imported lazily: taskiq is only
    needed with this backend).
    """

    def __init__(self, deps: Deps) -> None:
        from agentprobe_api import worker

        self._deps = deps
        self._worker = worker

    async def start(self) -> None:
        await self._worker.broker.startup()

    async def enqueue(self, run_id: uuid.UUID) -> None:
        await self._worker.start_run.kiq(str(run_id))

    async def cancel(self, run_id: uuid.UUID) -> None:
        # Attempt jobs see the status and stop; this summarizes what was saved.
        await self._worker.finalize_run.kiq(str(run_id))

    async def recover(self) -> None:
        stale_after = self._deps.settings.run_stale_after_s
        for run_id in await runstore.stale_runs(self._deps.sessions, stale_after):
            await self.enqueue(run_id)

    async def aclose(self) -> None:
        await self._worker.broker.shutdown()


def make_queue(deps: Deps) -> QueueBackend:
    if deps.settings.queue_backend == "redis":
        return RedisQueue(deps)
    return InlineQueue(deps)
