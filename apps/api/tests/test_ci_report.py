"""POST /ci/report (ADR 0018): ingesting a run the CLI already executed, and comparing it
with a branch's baseline.
"""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.main import create_app
from agentprobe_core.adapters.types import AgentResponse, MessageStep
from agentprobe_core.runner import AttemptResult, JudgeResult
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
    assert run["branch"] == "feature-x"
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
