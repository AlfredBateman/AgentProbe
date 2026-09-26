"""GET /runs/{id}/export?format=json|html (ADR 0018), including the XSS regression: a
`<script>` tag and an event-handler attribute in agent output must render as literal,
escaped text in the HTML export, never as live markup.
"""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from agentprobe_core.adapters.types import AgentResponse, MessageStep, ToolCallStep
from agentprobe_core.runner import AttemptResult, JudgeResult
from apitest import ClientFactory, SignUp
from runtest import SMOKE_YAML, make_project, start_run, wait_for_run

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]

XSS_SCRIPT = "<script>alert('xss')</script>"
XSS_ATTR = "<img src=x onerror=alert(1)>"


async def api_key_for(
    alice: httpx.AsyncClient, project_id: str, clients: ClientFactory
) -> httpx.AsyncClient:
    key = (await alice.post(f"/projects/{project_id}/api-keys", json={"label": "ci"})).json()["key"]
    return clients(headers={"Authorization": f"Bearer {key}"})


async def test_json_export_is_a_run_and_a_rebuilt_summary(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])

    r = await alice.get(f"/runs/{done['id']}/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["run"]["id"] == done["id"]
    assert body["run"]["status"] == "completed"
    summary = body["summary"]
    assert summary["suite"] == "smoke"
    assert summary["agent"] == "support-v1"
    assert len(summary["results"]) == 45
    assert len(summary["cases"]) == 9
    # The steps live on the full attempt, unlike the /runs/{id}/results listing.
    assert any(a["response"]["steps"] for a in summary["results"])


async def test_export_requires_ownership(sign_up: SignUp, app: FastAPI, demo_url: str) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    bob = await sign_up("bob@example.com")
    assert (await bob.get(f"/runs/{done['id']}/export")).status_code == 404


async def test_html_export_escapes_hostile_agent_output(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(
        alice, "http://127.0.0.1:9/chat", yaml=_xss_yaml(), agent_name="support-v1"
    )
    ci = await api_key_for(alice, ids["project_id"], clients)

    output = f"{XSS_SCRIPT} and {XSS_ATTR}"
    result = AttemptResult(
        case_id="hostile",
        attempt=0,
        input="say something",
        status="passed",
        response=AgentResponse(
            output=output,
            steps=[
                MessageStep(role="assistant", content=output),
                ToolCallStep(tool=XSS_SCRIPT, arguments={"payload": XSS_ATTR}),
            ],
            latency_ms=1.0,
            tool_calls_reported=True,
        ),
        judgments=[
            JudgeResult(judge="contains", status="pass", score=1.0, reason=f"found {XSS_ATTR}")
        ],
        score=1.0,
        latency_ms=1.0,
        started_at=datetime.now(UTC),
        duration_ms=1.0,
    )
    report = await ci.post(
        "/ci/report",
        json={
            "suite": "hostile",
            "agent": "support-v1",
            "results": [result.model_dump(mode="json")],
            "branch": "main",
        },
    )
    assert report.status_code == 201, report.text
    run_id = report.json()["run_id"]

    r = await alice.get(f"/runs/{run_id}/export", params={"format": "html"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    csp = r.headers["content-security-policy"]
    assert "default-src 'none'" in csp and "script-src" not in csp  # no script, ever
    html = r.text
    # The payloads must never appear as live markup: no unescaped '<script' or '<img' tag
    # anywhere, only their escaped text form.
    assert "<script>" not in html
    assert "<script " not in html
    assert "<img " not in html
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    # No external assets: everything is inline.
    assert "<link " not in html
    assert "cdn." not in html


def _xss_yaml() -> str:
    return """
suite: hostile
agent: support-v1
runs_per_case: 1
cases:
  - id: hostile
    input: "say something"
    expect:
      - judge: max_length
        max_chars: 5000
"""
