"""POST /ci/report (ADR 0018): ingesting a run the CLI already executed, and comparing it
with a branch's baseline.
"""

import sys
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe.push import Target, push
from agentprobe.push import payload as push_payload
from agentprobe_api.main import create_app
from agentprobe_core.adapters.python import PythonAdapter
from agentprobe_core.adapters.types import AgentResponse, MessageStep
from agentprobe_core.runner import AttemptResult, JudgeResult, RunSummary, run_suite
from agentprobe_core.suite import parse_suite_yaml
from apitest import ClientFactory, SignUp, bind_db, client_for, make_settings, signed_up
from runtest import SMALL_YAML, make_project

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]


def attempt(case_id: str, attempt: int, *, passed: bool, output: str = "ok") -> dict[str, object]:
    response = AgentResponse(
        output=output,
        steps=[MessageStep(role="assistant", content=output)],
        latency_ms=10.0,
        tool_calls_reported=True,
    )
    result = AttemptResult(
        case_id=case_id,
        attempt=attempt,
        input="hi",
        status="passed" if passed else "failed",
        response=response,
        judgments=[
            JudgeResult(
                judge="contains",
                status="pass" if passed else "fail",
                score=1.0 if passed else 0.0,
                reason="ok" if passed else "no match",
            )
        ],
        score=1.0 if passed else 0.0,
        latency_ms=10.0,
        started_at=datetime.now(UTC),
        duration_ms=10.0,
    )
    return result.model_dump(mode="json")


async def api_key_for(
    alice: httpx.AsyncClient, project_id: str, clients: ClientFactory
) -> httpx.AsyncClient:
    key = (await alice.post(f"/projects/{project_id}/api-keys", json={"label": "ci"})).json()["key"]
    return clients(headers={"Authorization": f"Bearer {key}"})


async def test_ingest_persists_a_completed_run_with_no_baseline(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await api_key_for(alice, ids["project_id"], clients)

    results = [attempt("greeting", n, passed=True) for n in range(2)] + [
        attempt("refund-outside-window", n, passed=True) for n in range(2)
    ]
    r = await ci.post(
        "/ci/report",
        json={
            "suite": "small",
            "agent": "support-v1",
            "results": results,
            "branch": "feature-x",
            "model": "model-a",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verdict"] == "no_baseline"
    assert body["comparison"] is None
    assert body["top_findings"] == []
    assert body["dashboard_url"] is None  # PUBLIC_WEB_URL not configured in tests

    run = (await alice.get(f"/runs/{body['run_id']}")).json()
    assert run["status"] == "completed"
    assert (run["branch"], run["model"]) == ("feature-x", "model-a")
    assert (run["agent_id"], run["agent_name"]) == (ids["agent_id"], None)
    assert run["pass_rate"] == 1.0


async def test_ingest_compares_against_a_baseline_and_flags_a_regression(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await api_key_for(alice, ids["project_id"], clients)

    baseline_results = [attempt("greeting", n, passed=True) for n in range(5)] + [
        attempt("refund-outside-window", n, passed=True) for n in range(5)
    ]
    baseline = await ci.post(
        "/ci/report",
        json={
            "suite": "small",
            "agent": "support-v1",
            "results": baseline_results,
            "runs_per_case": 5,
            "branch": "main",
        },
    )
    assert baseline.status_code == 201, baseline.text
    set_r = await alice.post(
        f"/projects/{ids['project_id']}/baseline",
        json={"branch": "main", "run_id": baseline.json()["run_id"]},
    )
    assert set_r.status_code == 201, set_r.text

    candidate_results = [attempt("greeting", n, passed=True) for n in range(5)] + [
        attempt("refund-outside-window", n, passed=False) for n in range(5)
    ]
    candidate = await ci.post(
        "/ci/report",
        json={
            "suite": "small",
            "agent": "support-v1",
            "results": candidate_results,
            "runs_per_case": 5,
            "branch": "pr-42",
            "baseline_branch": "main",
            "pr_number": 42,
        },
    )
    assert candidate.status_code == 201, candidate.text
    body = candidate.json()
    assert body["verdict"] == "regression"
    assert body["comparison"] is not None
    assert "refund-outside-window" in body["comparison"]["regressed"]

    run = (await alice.get(f"/runs/{body['run_id']}")).json()
    assert (run["branch"], run["pr_number"]) == ("pr-42", 42)


async def test_dashboard_url_is_built_when_public_web_url_is_configured(
    db: AsyncSession,
) -> None:
    app = bind_db(create_app(make_settings(public_web_url="https://dash.example.com/")), db)
    alice = client_for(app)
    try:
        await signed_up(alice, "alice@example.com")
        ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
        key = (
            await alice.post(f"/projects/{ids['project_id']}/api-keys", json={"label": "ci"})
        ).json()["key"]
        ci = client_for(app, headers={"Authorization": f"Bearer {key}"})
        try:
            r = await ci.post(
                "/ci/report",
                json={
                    "suite": "small",
                    "agent": "support-v1",
                    "results": [attempt("greeting", 0, passed=True)],
                    "branch": "main",
                },
            )
            assert r.status_code == 201, r.text
            assert (
                r.json()["dashboard_url"] == f"https://dash.example.com/runs/{r.json()['run_id']}"
            )
        finally:
            await ci.aclose()
    finally:
        await alice.aclose()


async def test_ingest_requires_an_api_key(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    r = await alice.post(
        "/ci/report",
        json={
            "suite": "small",
            "agent": "support-v1",
            "results": [attempt("greeting", 0, passed=True)],
            "branch": "main",
        },
    )
    assert r.status_code == 403


PY_YAML = """
suite: py
agent: py-bot
runs_per_case: 5
cases:
  - id: hello
    input: "hello"
    expect:
      - judge: contains
        value: "ok:"
"""


async def local_python_run(monkeypatch: pytest.MonkeyPatch, target: str) -> RunSummary:
    """A run of the CLI's python adapter, executed here as `agentprobe run` would."""
    with monkeypatch.context() as m:
        # The adapter refuses to load in a process that imported the server (ADR 0012);
        # this test process has, a real CLI process never does.
        m.delitem(sys.modules, "agentprobe_api")
        adapter = PythonAdapter(target)
    return await run_suite(parse_suite_yaml(PY_YAML), adapter)


async def test_a_pushed_python_adapter_run_is_compared_with_its_own_baseline(
    sign_up: SignUp, clients: ClientFactory, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=PY_YAML)
    ci = await api_key_for(alice, ids["project_id"], clients)
    key = ci.headers["authorization"].removeprefix("Bearer ")
    target = Target("https://api.test", key)

    async def pushed(summary: RunSummary, **fields: Any) -> dict[str, Any]:
        body = push_payload(summary, registered=False, mock=True, **fields)
        return await push(target, body, transport=httpx.ASGITransport(app=app))

    async def set_baseline(run_id: str) -> None:
        r = await alice.post(
            f"/projects/{ids['project_id']}/baseline", json={"branch": "main", "run_id": run_id}
        )
        assert r.status_code == 201, r.text

    # The registered agent's own baseline on the same suite and branch: it must not be the
    # one the python agent's runs are compared with.
    registered = await ci.post(
        "/ci/report",
        json={
            "suite": "py",
            "agent": "support-v1",
            "results": [attempt("hello", n, passed=False) for n in range(5)],
            "branch": "main",
        },
    )
    assert registered.status_code == 201, registered.text
    await set_baseline(registered.json()["run_id"])

    base = await pushed(await local_python_run(monkeypatch, "cli_agents:good"), branch="main")
    assert base["verdict"] == "no_baseline"
    await set_baseline(base["run_id"])

    baselines = f"/projects/{ids['project_id']}/baselines/main"
    mine = (await alice.get(baselines, params={"suite": "py", "agent_name": "py-bot"})).json()
    assert (mine["run_id"], mine["agent_id"], mine["agent_name"]) == (
        base["run_id"],
        None,
        "py-bot",
    )
    theirs = (await alice.get(baselines, params={"suite": "py", "agent": "support-v1"})).json()
    assert (theirs["run_id"], theirs["agent_id"]) == (registered.json()["run_id"], ids["agent_id"])

    candidate = await pushed(
        await local_python_run(monkeypatch, "cli_agents:bad"),
        branch="pr-7",
        baseline_branch="main",
        model="m-2",
    )
    assert candidate["verdict"] == "regression"  # 5/5 -> 0/5 against py-bot's baseline
    assert candidate["comparison"]["regressed"] == ["hello"]
    run = (await alice.get(f"/runs/{candidate['run_id']}")).json()
    assert (run["agent_id"], run["agent_name"], run["model"]) == (None, "py-bot", "m-2")


@pytest.mark.parametrize(
    ("agent_fields", "message"),
    [
        ({}, "exactly one of `agent`"),
        ({"agent": "support-v1", "agent_name": "x"}, "exactly one of `agent`"),
        ({"agent_name": "support-v1"}, "'support-v1' is a registered agent; send it as `agent`"),
    ],
    ids=["neither", "both", "registered-name"],
)
async def test_ingest_needs_one_unambiguous_agent_identity(
    sign_up: SignUp, clients: ClientFactory, agent_fields: dict[str, str], message: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await api_key_for(alice, ids["project_id"], clients)
    body = {
        "suite": "small",
        "results": [attempt("greeting", 0, passed=True)],
        "branch": "main",
        **agent_fields,
    }
    r = await ci.post("/ci/report", json=body)
    assert r.status_code == 422
    assert message in r.text


@pytest.mark.parametrize(
    ("field", "value"),
    [("suite", "nope"), ("agent", "nope")],
)
async def test_ingest_requires_an_existing_suite_and_agent(
    sign_up: SignUp, clients: ClientFactory, field: str, value: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await api_key_for(alice, ids["project_id"], clients)
    body = {
        "suite": "small",
        "agent": "support-v1",
        "results": [attempt("greeting", 0, passed=True)],
        "branch": "main",
    }
    body[field] = value
    r = await ci.post("/ci/report", json=body)
    assert r.status_code == 422


async def test_ingest_rejects_unknown_case_ids_duplicates_and_oversized_payloads(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await api_key_for(alice, ids["project_id"], clients)

    unknown_case = await ci.post(
        "/ci/report",
        json={
            "suite": "small",
            "agent": "support-v1",
            "results": [attempt("no-such-case", 0, passed=True)],
            "branch": "main",
        },
    )
    assert unknown_case.status_code == 422

    duplicate = await ci.post(
        "/ci/report",
        json={
            "suite": "small",
            "agent": "support-v1",
            "results": [attempt("greeting", 0, passed=True), attempt("greeting", 0, passed=True)],
            "branch": "main",
        },
    )
    assert duplicate.status_code == 422

    too_many = await ci.post(
        "/ci/report",
        json={
            "suite": "small",
            "agent": "support-v1",
            "results": [attempt("greeting", n, passed=True) for n in range(3)],
            "runs_per_case": 1,  # 2 cases x 1 run = 2 expected; 3 greeting attempts alone exceed it
            "branch": "main",
        },
    )
    assert too_many.status_code == 422

    empty = await ci.post(
        "/ci/report",
        json={"suite": "small", "agent": "support-v1", "results": [], "branch": "main"},
    )
    assert empty.status_code == 422
