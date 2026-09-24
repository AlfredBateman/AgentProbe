"""User B (by session or by B's API key) can't read or modify user A's resources.

Extend PROBES / SNAPSHOT and the `world` fixture whenever an endpoint takes a resource id.
"""

from dataclasses import dataclass

import httpx
import pytest

from apitest import ClientFactory, SignUp
from idor import Probe, assert_no_idor

pytestmark = pytest.mark.integration

PROBES = [
    Probe("GET", "/projects/{project_id}"),
    Probe("GET", "/projects/{project_id}/api-keys"),
    Probe("POST", "/projects/{project_id}/api-keys", {"label": "stolen"}),
    Probe("DELETE", "/projects/{project_id}/api-keys/{api_key_id}"),
]
SNAPSHOT = ["/projects", "/projects/{project_id}", "/projects/{project_id}/api-keys"]


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
async def world(sign_up: SignUp, clients: ClientFactory) -> World:
    alice = await sign_up("alice@example.com")
    project_id, api_key_id, _ = await make_project_with_key(alice, "alice-project")
    bob = await sign_up("bob@example.com")
    _, _, bob_key = await make_project_with_key(bob, "bob-project")
    return World(
        alice=alice,
        ids={"project_id": project_id, "api_key_id": api_key_id},
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
