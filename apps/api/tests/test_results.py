"""GET /runs/{id}/results (filters), GET /results/{id}/trace, and GET /runs/compare (ADR
0018). The "done when" scenario: /support/v1 then /support/v2 against the smoke suite,
GET /runs/compare returns `regression` naming the newly-failing refund case, and a run
compared with itself returns `no_change`.
"""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI

from apitest import SignUp
from runtest import SMOKE_YAML, SUPPORT_RESPONSE, make_project, start_run, wait_for_run

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]


async def test_v1_then_v2_compare_is_a_regression_and_v1_vs_v1_is_no_change(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)

    v1_run = await start_run(alice, ids["suite_id"])
    v1_done = await wait_for_run(alice, app, v1_run["id"])
    assert v1_done["status"] == "completed"

    v1_again_run = await start_run(alice, ids["suite_id"])
    v1_again_done = await wait_for_run(alice, app, v1_again_run["id"])
    assert v1_again_done["status"] == "completed"

    # v1 vs v1 (a fresh run of the exact same agent/suite): no_change.
    same = await alice.get("/runs/compare", params={"a": v1_done["id"], "b": v1_again_done["id"]})
    assert same.status_code == 200, same.text
    same_body = same.json()
    assert same_body["report"]["verdict"] == "no_change"
    assert same_body["baseline_run_id"] == v1_done["id"]
    assert same_body["candidate_run_id"] == v1_again_done["id"]

    # Re-point the same agent at /support/v2/chat (the planted 45-day refund window) and run
    # the same suite again: same suite_id, so it's a real apples-to-apples comparison.
    repoint = await alice.put(
        f"/agents/{ids['agent_id']}",
        json={
            "config": {
                "adapter_type": "http",
                "url": f"{demo_url}/support/v2/chat",
                "allow_private": True,
                "response": SUPPORT_RESPONSE,
            }
        },
    )
    assert repoint.status_code == 200, repoint.text
    v2_run = await start_run(alice, ids["suite_id"])
    v2_done = await wait_for_run(alice, app, v2_run["id"])
    assert v2_done["status"] == "completed"

    regression = await alice.get("/runs/compare", params={"a": v1_done["id"], "b": v2_done["id"]})
    assert regression.status_code == 200, regression.text
    report = regression.json()["report"]
    assert report["verdict"] == "regression"
    assert "refund-outside-window" in report["newly_failing"]
    assert "refund-outside-window" in report["regressed"]


async def test_compare_rejects_runs_of_different_suites(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    a = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    b = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run_a = await wait_for_run(alice, app, (await start_run(alice, a["suite_id"]))["id"])
    run_b = await wait_for_run(alice, app, (await start_run(alice, b["suite_id"]))["id"])
    r = await alice.get("/runs/compare", params={"a": run_a["id"], "b": run_b["id"]})
    assert r.status_code == 422


async def test_results_are_listed_and_filterable(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    run_id = done["id"]

    all_results = await alice.get(f"/runs/{run_id}/results")
    assert all_results.status_code == 200
    rows = all_results.json()
    assert len(rows) == 40  # 8 cases x 5 runs
    assert {r["case"] for r in rows} == {
        "greeting",
        "refund-outside-window",
        "refund-inside-window",
        "order-status",
        "system-prompt-leak",
        "api-key-leak",
        "unauthorized-delete",
        "off-topic",
    }
    assert all(r["label"] in {"stable-pass", "stable-fail", "flaky"} for r in rows)
    greeting = next(r for r in rows if r["case"] == "greeting")
    assert greeting["judgments"], "attempt-scope judgments should be attached"

    by_case = await alice.get(f"/runs/{run_id}/results", params={"case": "greeting"})
    assert {r["case"] for r in by_case.json()} == {"greeting"}
    assert len(by_case.json()) == 5

    # Each filter returns exactly the matching rows of the full listing: never empty by
    # accident (the smoke suite always has passes), and never more.
    def ids(listed: list[dict[str, Any]]) -> list[str]:
        return [r["id"] for r in listed]

    by_status = await alice.get(f"/runs/{run_id}/results", params={"status": "passed"})
    passed = ids([r for r in rows if r["status"] == "passed"])
    assert passed and ids(by_status.json()) == passed

    # Which case the seeded flakiness hits depends on attempt order, so compare with the
    # listing's own labels rather than naming a case.
    flaky = await alice.get(f"/runs/{run_id}/results", params={"label": "flaky"})
    assert ids(flaky.json()) == ids([r for r in rows if r["label"] == "flaky"])
    stable = await alice.get(f"/runs/{run_id}/results", params={"label": "stable-pass"})
    assert {r["case"] for r in stable.json()} >= {"greeting", "refund-outside-window"}

    none_such = await alice.get(f"/runs/{run_id}/results", params={"case": "nope"})
    assert none_such.json() == []


async def test_trace_returns_the_full_attempt(sign_up: SignUp, app: FastAPI, demo_url: str) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    listed = (
        await alice.get(f"/runs/{done['id']}/results", params={"case": "order-status"})
    ).json()
    result_id = listed[0]["id"]

    trace = await alice.get(f"/results/{result_id}/trace")
    assert trace.status_code == 200, trace.text
    body = trace.json()
    assert body["case"] == "order-status"
    assert body["output"]
    assert body["steps"]  # the full trace, unlike the results listing
    tool_calls = [s for s in body["steps"] if s["type"] == "tool_call"]
    assert any(s["tool"] == "lookup_order" for s in tool_calls)


async def test_trace_404s_for_an_unknown_result(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.get(f"/results/{uuid.uuid4()}/trace")
    assert r.status_code == 404


async def test_compare_requires_owned_runs(sign_up: SignUp, app: FastAPI, demo_url: str) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])

    missing = await alice.get("/runs/compare", params={"a": done["id"], "b": str(uuid.uuid4())})
    assert missing.status_code == 404

    bob = await sign_up("bob@example.com")
    denied = await bob.get("/runs/compare", params={"a": done["id"], "b": done["id"]})
    assert denied.status_code == 404
