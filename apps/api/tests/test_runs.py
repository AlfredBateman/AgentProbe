"""Server runs on the inline backend against the real demo agents (mock mode, mock LLM),
persisted to the Neon test database: lifecycle, persistence, SSE, cancel, failure,
crash recovery and idempotency.
"""

import asyncio
import uuid
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import runstore
from agentprobe_api.main import create_app
from agentprobe_api.models import Judgment, Run, RunCaseSummary, RunResult, TestCase, Trace
from agentprobe_api.queue import InlineQueue, finalize
from agentprobe_api.security import encode_token
from agentprobe_core.runner import execute_attempt
from apitest import ClientFactory, SignUp, bind_db, make_settings
from runtest import (
    SMOKE_YAML,
    NullQueue,
    deps_of,
    make_project,
    parse_sse,
    start_run,
    wait_for_run,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]


@pytest.fixture
def app(db: AsyncSession) -> FastAPI:
    settings = make_settings(run_max_retries=1, run_backoff_base_s=0.01)
    return bind_db(create_app(settings), db)


async def case_labels(db: AsyncSession, run_id: uuid.UUID) -> dict[str, str]:
    rows = await db.execute(
        select(TestCase.case_key, RunCaseSummary.label)
        .join(TestCase, TestCase.id == RunCaseSummary.case_id)
        .where(RunCaseSummary.run_id == run_id)
    )
    return {key: label for key, label in rows.tuples()}


async def count(db: AsyncSession, model: Any, *where: Any) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def test_a_suite_run_completes_with_everything_persisted(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"], model="rule-engine")
    assert (run["status"], run["attempts_total"], run["model"]) == ("queued", 45, "rule-engine")

    done = await wait_for_run(alice, app, run["id"])
    assert done["status"] == "completed", done
    assert (done["attempts_done"], done["error"]) == (45, None)
    assert done["pass_rate"] >= 0.9  # everything passes but the seeded-flaky order lookup
    assert done["ci_lower"] <= done["pass_rate"] <= done["ci_upper"]
    assert done["started_at"] and done["finished_at"]
    assert done["total_tokens"] > 0

    run_id = uuid.UUID(run["id"])
    assert await count(db, RunResult, RunResult.run_id == run_id) == 45
    results = (await db.scalars(select(RunResult).where(RunResult.run_id == run_id))).all()
    assert {r.status for r in results} <= {"passed", "failed"}
    assert all(r.detail["case_id"] and r.output for r in results)
    traces = (
        await db.scalars(select(Trace).join(RunResult).where(RunResult.run_id == run_id))
    ).all()
    assert len(traces) == 45
    tool_calls = [s for t in traces for s in t.steps if s["type"] == "tool_call"]
    assert {"tool": "lookup_order", "arguments": {"order_id": "1042"}}.items() <= next(
        c for c in tool_calls if c["tool"] == "lookup_order"
    ).items()
    judgments = (
        await db.scalars(select(Judgment).join(RunResult).where(RunResult.run_id == run_id))
    ).all()
    # 5 runs of each case's judges: 3 + 2 + 1 + 2 + 2 + 1 + 1 + 1 + 1 (instruction-injection)
    assert len(judgments) == 5 * 14
    assert {j.status for j in judgments} <= {"pass", "fail"}
    assert all(j.passed == (j.status == "pass") for j in judgments)
    summaries = (
        await db.scalars(select(RunCaseSummary).where(RunCaseSummary.run_id == run_id))
    ).all()
    assert len(summaries) == 9
    assert sum(s.attempts for s in summaries) == 45
    assert {s.label for s in summaries} <= {"stable-pass", "flaky"}


async def test_the_snapshot_keeps_the_secret_out_and_the_run_still_sends_it(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    # /support/v1 deletes orders only with X-Admin-Context: proof the header was sent.
    yaml = SMOKE_YAML.replace("runs_per_case: 5", "runs_per_case: 1")
    ids = await make_project(
        alice,
        f"{demo_url}/support/v1/chat",
        yaml=yaml,
        auth_header={"name": "X-Admin-Context", "value": "true"},
    )
    run = await start_run(alice, ids["suite_id"])
    await wait_for_run(alice, app, run["id"])
    row = await db.get(Run, uuid.UUID(run["id"]))
    assert row is not None
    snapshot = row.config_snapshot
    assert snapshot["agent"]["secret_ref"]
    assert "X-Admin-Context" not in str(snapshot)
    labels = await case_labels(db, row.id)
    assert labels["unauthorized-delete"] == "stable-fail"  # it deleted: the header arrived


async def test_sse_streams_progress_to_completion(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    queue = app.state.queue
    app.state.queue = NullQueue()  # hold the run until the stream is connected
    run = await start_run(alice, ids["suite_id"])
    run_id = uuid.UUID(run["id"])

    stream = asyncio.create_task(alice.get(f"/runs/{run_id}/stream"))
    async with asyncio.timeout(10):
        while run_id not in app.state.bus._subscribers:  # noqa: ASYNC110 (no hook to await)
            await asyncio.sleep(0.01)
    app.state.queue = queue
    await queue.enqueue(run_id)
    response = await asyncio.wait_for(stream, 60)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert events[0] == {**events[0], "type": "snapshot", "status": "queued", "done": 0}
    attempts = [e for e in events if e["type"] == "attempt"]
    assert len(attempts) == 4
    assert sorted(e["done"] for e in attempts) == [1, 2, 3, 4]
    assert all(set(e) == {"type", "case", "attempt", "status", "done", "total"} for e in attempts)
    assert [e["status"] for e in events if e["type"] == "status"] == ["running", "completed"]


async def test_stream_token_fallback(
    sign_up: SignUp, clients: ClientFactory, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    app.state.queue = NullQueue()
    first = (await start_run(alice, ids["suite_id"]))["id"]
    other = (await start_run(alice, ids["suite_id"]))["id"]
    for run_id in (first, other):  # ended runs: the stream sends the snapshot and closes
        assert (await alice.post(f"/runs/{run_id}/cancel")).status_code == 200

    r = await alice.post(f"/runs/{first}/stream-token")
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["expires_in"] == 60
    anonymous = clients(headers={"Origin": "https://elsewhere.test"})
    ok = await anonymous.get(f"/runs/{first}/stream", params={"token": token})
    assert ok.status_code == 200, ok.text
    assert parse_sse(ok.text) == [
        {**parse_sse(ok.text)[0], "type": "snapshot", "status": "cancelled"}
    ]

    assert (
        await anonymous.get(f"/runs/{other}/stream", params={"token": token})
    ).status_code == 401
    assert (
        await anonymous.get(f"/runs/{first}/stream", params={"token": "nope"})
    ).status_code == 401
    expired = encode_token(
        app.state.settings.jwt_secret, "stream", uuid.uuid4(), timedelta(seconds=-1), run_id=first
    )
    access = alice.cookies["access_token"]  # a session token is not a stream token
    for bad in (expired, access):
        r = await anonymous.get(f"/runs/{first}/stream", params={"token": bad})
        assert r.status_code == 401
    assert (await anonymous.get(f"/runs/{first}/stream")).status_code == 401


async def test_stream_token_needs_a_user_session_and_ownership(
    sign_up: SignUp, clients: ClientFactory, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    app.state.queue = NullQueue()
    run_id = (await start_run(alice, ids["suite_id"]))["id"]
    await alice.post(f"/runs/{run_id}/cancel")
    key = (
        await alice.post(f"/projects/{ids['project_id']}/api-keys", json={"label": "ci"})
    ).json()["key"]
    ci = clients(headers={"Authorization": f"Bearer {key}"})
    assert (await ci.post(f"/runs/{run_id}/stream-token")).status_code == 403
    assert (await ci.get(f"/runs/{run_id}/stream")).status_code == 200  # headers work for CI
    bob = await sign_up("bob@example.com")
    assert (await bob.post(f"/runs/{run_id}/stream-token")).status_code == 404
    assert (await bob.get(f"/runs/{run_id}/stream")).status_code == 404


async def test_cancel_mid_run_keeps_a_summary_of_what_finished(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str
) -> None:
    deps = deps_of(app)
    one_at_a_time = deps.settings.model_copy(update={"run_concurrency": 1})
    app.state.queue = InlineQueue(replace(deps, settings=one_at_a_time))
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    run_id = uuid.UUID(run["id"])
    async with app.state.bus.subscribe(run_id) as subscription:
        while (event := await subscription.next(30)) is not None and event["type"] != "attempt":
            pass
    r = await alice.post(f"/runs/{run_id}/cancel")
    assert (r.status_code, r.json()["status"]) == (200, "cancelled")
    done = await wait_for_run(alice, app, run["id"])
    assert done["status"] == "cancelled"
    assert 0 < done["attempts_done"] < 40
    assert done["pass_rate"] is not None  # summarized over the finished attempts
    assert await count(db, RunResult, RunResult.run_id == run_id) == done["attempts_done"]
    assert (await alice.post(f"/runs/{run_id}/cancel")).status_code == 409


async def test_cancelling_a_queued_run_means_it_never_runs(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    queue, app.state.queue = app.state.queue, NullQueue()
    run = await start_run(alice, ids["suite_id"])
    assert (await alice.post(f"/runs/{run['id']}/cancel")).json()["status"] == "cancelled"
    await queue.enqueue(uuid.UUID(run["id"]))
    await queue.join()
    done = (await alice.get(f"/runs/{run['id']}")).json()
    assert (done["status"], done["attempts_done"], done["started_at"]) == ("cancelled", 0, None)


async def test_an_unreachable_agent_fails_the_run_after_retries(
    sign_up: SignUp, app: FastAPI, db: AsyncSession
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(
        alice, "http://127.0.0.1:9/chat", yaml=SMOKE_YAML, max_retries=0
    )  # the discard port: nothing listens
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    assert done["status"] == "failed"
    assert done["error"].startswith("unreachable error: could not connect")
    rows = (
        await db.scalars(select(RunResult).where(RunResult.run_id == uuid.UUID(run["id"])))
    ).all()
    # The attempts in flight when the first one failed the run may land; nothing after.
    assert 1 <= len(rows) == done["attempts_done"] <= app.state.settings.run_concurrency
    assert {(r.error_kind, r.retries) for r in rows} == {("unreachable", 1)}
    assert done["pass_rate"] == 0.0  # summarized over what was saved


@pytest.mark.parametrize(
    ("yaml", "message"),
    [
        (SMOKE_YAML.replace("agent: support-v1", "agent: nobody"), "isn't in this project"),
        (
            "suite: s\nagent: support-v1\ncases:\n  - id: a\n    attack: tool_misuse\n"
            "    expect:\n      - {judge: contains, value: x}\n",
            "isn't wired into run execution yet",
        ),
    ],
)
async def test_unrunnable_suites_are_422(
    sign_up: SignUp, app: FastAPI, demo_url: str, yaml: str, message: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=yaml)
    r = await alice.post(f"/suites/{ids['suite_id']}/runs", json={})
    assert r.status_code == 422
    assert message in r.json()["error"]["message"]
    bad = await alice.post(f"/suites/{ids['suite_id']}/runs", json={"runs_per_case": 0})
    assert bad.status_code == 422


async def test_a_crashed_run_resumes_without_redoing_saved_attempts(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    app.state.queue = NullQueue()
    run = await start_run(alice, ids["suite_id"], runs_per_case=3)
    run_id = uuid.UUID(run["id"])
    deps = deps_of(app)
    # The dead process had claimed the run and saved two attempts (marked failed here, so
    # re-running them would show).
    assert await runstore.claim(deps.sessions, run_id)
    plan = await runstore.load_plan(deps.sessions, run_id, deps.secret_box)
    assert plan is not None
    adapter = plan.adapter()
    for n in (0, 1):
        result = await execute_attempt(plan.case("greeting"), adapter, attempt=n)
        failed = result.model_copy(update={"status": "failed", "score": 0.0})
        assert await runstore.save_attempt(deps.sessions, plan, failed) == n + 1
    await runstore.close_adapter(adapter)

    queue = InlineQueue(deps)
    await queue.recover()  # at startup every live inline run is orphaned
    await queue.join()
    done = (await alice.get(f"/runs/{run_id}")).json()
    assert (done["status"], done["attempts_done"]) == ("completed", 6)
    rows = await db.execute(
        select(TestCase.case_key, RunCaseSummary.passes)
        .join(TestCase, TestCase.id == RunCaseSummary.case_id)
        .where(RunCaseSummary.run_id == run_id)
    )
    passes = {key: n for key, n in rows.tuples()}
    # attempts 0 and 1 kept their saved (failed) results; only attempt 2 ran
    assert passes == {"greeting": 1, "refund-outside-window": 3}


async def test_an_unrecoverable_run_is_marked_failed(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    app.state.queue = NullQueue()
    run = await start_run(alice, ids["suite_id"])
    run_id = uuid.UUID(run["id"])
    row = await db.get(Run, run_id)
    assert row is not None
    broken = {
        **row.config_snapshot,
        "agent": {**row.config_snapshot["agent"], "adapter_type": "mcp"},
    }
    await db.execute(update(Run).where(Run.id == run_id).values(config_snapshot=broken))
    await db.commit()
    queue = InlineQueue(deps_of(app))
    await queue.recover()
    await queue.join()
    done = (await alice.get(f"/runs/{run_id}")).json()
    assert done["status"] == "failed"
    assert done["error"].startswith("agent config:")


async def test_saves_are_idempotent(
    sign_up: SignUp, app: FastAPI, db: AsyncSession, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat")
    run = await start_run(alice, ids["suite_id"])
    await wait_for_run(alice, app, run["id"])
    run_id = uuid.UUID(run["id"])
    deps = deps_of(app)
    plan = await runstore.load_plan(deps.sessions, run_id, deps.secret_box)
    assert plan is not None
    results = await runstore.load_attempts(deps.sessions, run_id)
    assert len(results) == 4
    before = await count(db, Judgment)

    await db.execute(update(Run).where(Run.id == run_id).values(status="running"))
    await db.commit()
    assert await runstore.save_attempt(deps.sessions, plan, results[0]) is None  # redelivered
    await finalize(deps, plan)  # a second finalize
    await finalize(deps, plan)
    assert await count(db, RunResult, RunResult.run_id == run_id) == 4
    assert await count(db, Judgment) == before  # case-scope consistency judgments replaced
    assert await count(db, Judgment, Judgment.run_id == run_id) == 1
    assert await count(db, RunCaseSummary, RunCaseSummary.run_id == run_id) == 2
    rebuilt = await runstore.load_attempts(deps.sessions, run_id)
    assert sorted(r.model_dump_json() for r in rebuilt) == sorted(
        r.model_dump_json() for r in results
    )
