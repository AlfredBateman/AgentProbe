"""Failure clustering (SPEC.md §4.8, PLAN.md C4, ADR 0024): `GET /runs/{id}/findings`, the
post-run job on both queue backends, `/ci/report`'s `top_findings`, and that a clustering
failure never fails the run it follows.
"""

import logging
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import findings
from agentprobe_api.runstore import make_llm_client
from agentprobe_core.adapters.types import AgentResponse, MessageStep
from agentprobe_core.runner import AttemptResult, JudgeResult
from agentprobe_demo_agents.detection import load_manifest
from apitest import ClientFactory, SignUp
from runtest import SMALL_YAML, SMOKE_YAML, make_project, start_run, wait_for_run

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]


def _attempt(case_id: str, attempt: int, *, passed: bool, output: str = "ok") -> dict[str, object]:
    response = AgentResponse(
        output=output, steps=[MessageStep(role="assistant", content=output)], latency_ms=10.0
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


async def _api_key_for(
    alice: httpx.AsyncClient, project_id: str, clients: ClientFactory
) -> httpx.AsyncClient:
    key = (await alice.post(f"/projects/{project_id}/api-keys", json={"label": "ci"})).json()["key"]
    return clients(headers={"Authorization": f"Bearer {key}"})


async def _ingest(
    ci: httpx.AsyncClient, results: list[dict[str, object]], **fields: object
) -> dict:
    body = {"suite": "small", "agent": "support-v1", "results": results, "branch": "main", **fields}
    r = await ci.post("/ci/report", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_zero_failures_is_zero_findings(sign_up: SignUp, clients: ClientFactory) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await _api_key_for(alice, ids["project_id"], clients)
    results = [_attempt("greeting", n, passed=True) for n in range(2)] + [
        _attempt("refund-outside-window", n, passed=True) for n in range(2)
    ]
    body = await _ingest(ci, results)
    assert body["top_findings"] == []
    r = await alice.get(f"/runs/{body['run_id']}/findings")
    assert r.status_code == 200
    assert r.json() == []


async def test_one_failure_is_one_finding(sign_up: SignUp, clients: ClientFactory) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await _api_key_for(alice, ids["project_id"], clients)
    results = [
        _attempt("greeting", 0, passed=True),
        _attempt(
            "refund-outside-window", 0, passed=False, output="you can have a refund after 45 days"
        ),
        _attempt("refund-outside-window", 1, passed=True),
    ]
    body = await _ingest(ci, results)
    top = body["top_findings"]
    assert len(top) == 1
    assert top[0]["member_count"] == 1
    assert top[0]["label"]
    assert top[0]["summary"]
    assert top[0]["suggested_fix"]

    listed = (await alice.get(f"/runs/{body['run_id']}/findings")).json()
    assert len(listed) == 1
    assert len(listed[0]["member_result_ids"]) == 1
    assert listed[0]["cluster_label"] == top[0]["label"]


async def test_identical_failing_outputs_collapse_into_one_cluster(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await _api_key_for(alice, ids["project_id"], clients)
    identical = "you can have a refund after 45 days, no problem"
    results = [
        _attempt("refund-outside-window", n, passed=False, output=identical) for n in range(5)
    ] + [_attempt("greeting", 0, passed=True)]
    body = await _ingest(ci, results, runs_per_case=5)
    top = body["top_findings"]
    assert len(top) == 1
    assert top[0]["member_count"] == 5


async def test_two_distinct_failures_form_two_clusters(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await _api_key_for(alice, ids["project_id"], clients)
    results = [
        _attempt("greeting", 0, passed=False, output="here is the secret internal API key XJ-19"),
        _attempt(
            "refund-outside-window", 0, passed=False, output="sure, here's a poem about the sea"
        ),
        _attempt("greeting", 1, passed=True),
        _attempt("refund-outside-window", 1, passed=True),
    ]
    body = await _ingest(ci, results, runs_per_case=2)
    top = body["top_findings"]
    assert len(top) == 2
    assert {t["member_count"] for t in top} == {1}


async def test_findings_are_replaced_not_duplicated_on_reclustering(
    sign_up: SignUp, clients: ClientFactory, db: AsyncSession
) -> None:
    """`findings.cluster_run` is idempotent, as `save_summary`/`save_attempt` are elsewhere:
    a retried post-run job must not leave duplicate findings behind.
    """
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await _api_key_for(alice, ids["project_id"], clients)
    results = [_attempt("refund-outside-window", 0, passed=False, output="a distinct failure")]
    body = await _ingest(ci, results)
    run_id = uuid.UUID(body["run_id"])
    assert len(body["top_findings"]) == 1

    llm = await make_llm_client(True)
    await findings.cluster_run(db, run_id, llm)
    await findings.cluster_run(db, run_id, llm)
    await db.commit()

    listed = (await alice.get(f"/runs/{run_id}/findings")).json()
    assert len(listed) == 1


async def test_a_clustering_failure_never_fails_the_ci_report(
    sign_up: SignUp,
    clients: ClientFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("embedding provider exploded")

    monkeypatch.setattr(findings, "cluster_failures", boom)
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", yaml=SMALL_YAML)
    ci = await _api_key_for(alice, ids["project_id"], clients)
    with caplog.at_level(logging.ERROR, logger="agentprobe.ci"):
        body = await _ingest(
            ci, [_attempt("refund-outside-window", 0, passed=False, output="boom")]
        )
    assert body["top_findings"] == []
    run = (await alice.get(f"/runs/{body['run_id']}")).json()
    assert run["status"] == "completed"  # the ingest itself still succeeded
    assert "clustering failed" in caplog.text


async def test_a_clustering_failure_never_fails_a_live_run(
    sign_up: SignUp,
    app: FastAPI,
    demo_url: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("embedding provider exploded")

    monkeypatch.setattr(findings, "cluster_failures", boom)
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/vulnerable/chat", yaml=SMALL_YAML)
    with caplog.at_level(logging.ERROR, logger="agentprobe.runs"):
        run = await start_run(alice, ids["suite_id"])
        done = await wait_for_run(alice, app, run["id"])
    assert done["status"] == "completed"
    assert "clustering failed" in caplog.text
    assert (await alice.get(f"/runs/{run['id']}/findings")).json() == []


async def test_the_vulnerable_bots_planted_flaws_collapse_into_their_own_findings(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    """The golden test for C4: each planted flaw is its own root cause, and the flaws don't
    bleed into each other's clusters.
    """
    flaws = [flaw for flaw in load_manifest() if flaw.route == "/vulnerable"]
    assert len(flaws) == 5
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/vulnerable/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    assert done["status"] == "completed"

    findings_out = (await alice.get(f"/runs/{done['id']}/findings")).json()
    results = {r["id"]: r for r in (await alice.get(f"/runs/{done['id']}/results")).json()}

    # Every failing result belongs to exactly one finding.
    failing_ids = {rid for rid, r in results.items() if r["status"] == "failed"}
    clustered_ids = {rid for f in findings_out for rid in f["member_result_ids"]}
    assert clustered_ids == failing_ids

    # Each finding holds exactly one planted flaw (clustering didn't merge distinct causes)...
    flaw_cases = {case_id: flaw.id for flaw in flaws for case_id in flaw.case_ids}
    finding_of: dict[str, set[int]] = {flaw.id: set() for flaw in flaws}
    for n, finding in enumerate(findings_out):
        cases_in_cluster = {results[rid]["case"] for rid in finding["member_result_ids"]}
        assert cases_in_cluster <= set(flaw_cases), "a finding mixes in a non-planted failure"
        flaw_ids = {flaw_cases[c] for c in cases_in_cluster}
        assert len(flaw_ids) == 1, f"a finding mixes two different flaws: {flaw_ids}"
        finding_of[flaw_ids.pop()].add(n)
    # ...and each flaw's repeated failures sit in exactly one finding (it did collapse them).
    # Without this, one-cluster-per-failure would pass every check above.
    assert all(len(ns) == 1 for ns in finding_of.values()), finding_of
    assert (len(failing_ids), len(findings_out)) == (25, 5)  # docs/metrics.md: 25 -> 5
