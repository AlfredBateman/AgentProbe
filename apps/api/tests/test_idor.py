"""User B (by session or by B's API key) can't read or modify user A's resources.

Extend PROBES / SNAPSHOT and the `world` fixture whenever an endpoint takes a resource id.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.models import RunResult, TestCase
from agentprobe_core.adapters.types import AgentResponse, MessageStep
from agentprobe_core.runner import AttemptResult
from apitest import ClientFactory, SignUp
from idor import Probe, assert_no_idor
from runtest import NullQueue

pytestmark = pytest.mark.integration

HTTP_CONFIG = {"adapter_type": "http", "url": "https://agent.example.com/chat"}
VALID_YAML = """
suite: demo-suite
agent: demo-bot
cases:
  - id: c1
    input: "hi"
    expect:
      - judge: contains
        value: "ok"
"""
A_RANDOM_UUID = str(uuid.uuid4())  # a syntactically valid, otherwise-unused id for probe bodies

PROBES = [
    Probe("GET", "/projects/{project_id}"),
    Probe("GET", "/projects/{project_id}/api-keys"),
    Probe("POST", "/projects/{project_id}/api-keys", {"label": "stolen"}),
    Probe("DELETE", "/projects/{project_id}/api-keys/{api_key_id}"),
    Probe("GET", "/projects/{project_id}/agents"),
    Probe("POST", "/projects/{project_id}/agents", {"name": "stolen", "config": HTTP_CONFIG}),
    Probe("GET", "/agents/{agent_id}"),
    Probe("PUT", "/agents/{agent_id}", {"name": "renamed"}),
    Probe("DELETE", "/agents/{agent_id}"),
    Probe("GET", "/projects/{project_id}/suites"),
    Probe("POST", "/projects/{project_id}/suites", {"yaml": VALID_YAML}),
    Probe("PUT", "/suites/{suite_id}", {"yaml": VALID_YAML}),
    Probe("POST", "/suites/{suite_id}/runs", {}),
    Probe("GET", "/runs/{run_id}"),
    Probe("POST", "/runs/{run_id}/cancel"),
    Probe("POST", "/runs/{run_id}/stream-token"),
    Probe("GET", "/runs/{run_id}/stream"),
    Probe("GET", "/runs/{run_id}/results"),
    Probe("GET", "/results/{result_id}/trace"),
    Probe("GET", "/runs/compare?a={run_id}&b={run_id}"),
    Probe("GET", "/runs/{run_id}/export"),
    Probe("POST", "/runs/{run_id}/share", {}),
    Probe("DELETE", "/runs/{run_id}/share"),
    Probe("POST", "/projects/{project_id}/baseline", {"branch": "main", "run_id": A_RANDOM_UUID}),
    Probe("GET", "/projects/{project_id}/baselines/main"),
]
SNAPSHOT = [
    "/projects",
    "/projects/{project_id}",
    "/projects/{project_id}/api-keys",
    "/projects/{project_id}/agents",
    "/agents/{agent_id}",
    "/projects/{project_id}/suites",
    "/runs/{run_id}",
]


async def make_project_with_key(client: httpx.AsyncClient, name: str) -> tuple[str, str, str]:
    project = (await client.post("/projects", json={"name": name})).json()
    key = (await client.post(f"/projects/{project['id']}/api-keys", json={"label": "ci"})).json()
    return project["id"], key["id"], key["key"]


@dataclass
class World:
    alice: httpx.AsyncClient
    ids: dict[str, str]
    intruders: dict[str, httpx.AsyncClient]


@pytest.fixture
async def world(sign_up: SignUp, clients: ClientFactory, app: FastAPI, db: AsyncSession) -> World:
    app.state.queue = NullQueue()  # runs are created but never executed here
    alice = await sign_up("alice@example.com")
    project_id, api_key_id, _ = await make_project_with_key(alice, "alice-project")
    agent = (
        await alice.post(
            f"/projects/{project_id}/agents", json={"name": "demo-bot", "config": HTTP_CONFIG}
        )
    ).json()
    suite = (await alice.post(f"/projects/{project_id}/suites", json={"yaml": VALID_YAML})).json()
    run = (await alice.post(f"/suites/{suite['id']}/runs", json={})).json()

    # A result row for the /results/{id}/trace probe: the run itself never executes here
    # (NullQueue), so it's inserted directly, as an attempt a real run would have produced.
    case_id = await db.scalar(
        select(TestCase.id).where(TestCase.suite_id == uuid.UUID(suite["id"]))
    )
    attempt = AttemptResult(
        case_id="c1",
        attempt=0,
        input="hi",
        status="passed",
        response=AgentResponse(
            output="ok", steps=[MessageStep(role="assistant", content="ok")], latency_ms=1.0
        ),
        score=1.0,
        latency_ms=1.0,
        started_at=datetime.now(UTC),
        duration_ms=1.0,
    )
    result = RunResult(
        run_id=uuid.UUID(run["id"]),
        case_id=case_id,
        attempt=0,
        status="passed",
        output="ok",
        detail=attempt.model_dump(mode="json", exclude={"response": {"steps"}}),
    )
    db.add(result)
    await db.flush()

    bob = await sign_up("bob@example.com")
    _, _, bob_key = await make_project_with_key(bob, "bob-project")
    return World(
        alice=alice,
        ids={
            "project_id": project_id,
            "api_key_id": api_key_id,
            "agent_id": agent["id"],
            "suite_id": suite["id"],
            "run_id": run["id"],
            "result_id": str(result.id),
        },
        intruders={
            "bob_session": bob,
            "bob_api_key": clients(headers={"Authorization": f"Bearer {bob_key}"}),
        },
    )


@pytest.mark.parametrize("intruder", ["bob_session", "bob_api_key"])
async def test_other_user_cannot_touch_resources(world: World, intruder: str) -> None:
    await assert_no_idor(
        owner=world.alice,
        intruder=world.intruders[intruder],
        ids=world.ids,
        probes=PROBES,
        snapshot_paths=SNAPSHOT,
    )


@pytest.mark.parametrize("intruder", ["bob_session", "bob_api_key"])
async def test_listing_excludes_other_users(world: World, intruder: str) -> None:
    r = await world.intruders[intruder].get("/projects")
    assert r.status_code == 200
    assert world.ids["project_id"] not in {p["id"] for p in r.json()}
