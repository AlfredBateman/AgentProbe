import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.main import create_app
from agentprobe_api.models import ApiKey
from agentprobe_api.security import sha256
from apitest import ClientFactory, SignUp, bind_db, client_for, make_settings, signed_up

pytestmark = pytest.mark.integration


async def new_project(client: httpx.AsyncClient, name: str = "demo") -> dict[str, str]:
    r = await client.post("/projects", json={"name": name, "description": "d"})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def new_key(client: httpx.AsyncClient, project_id: str) -> dict[str, str]:
    r = await client.post(f"/projects/{project_id}/api-keys", json={"label": "ci"})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def keyed(clients: ClientFactory, key: str) -> httpx.AsyncClient:
    """An API-key client: no cookies, no Origin needed."""
    return clients(headers={"Authorization": f"Bearer {key}", "Origin": ""})


async def test_create_list_get_projects(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    a = await new_project(alice, "a")
    b = await new_project(alice, "b")
    assert [p["id"] for p in (await alice.get("/projects")).json()] == [a["id"], b["id"]]
    assert (await alice.get(f"/projects/{a['id']}")).json() == a
    assert (await alice.get("/projects/00000000-0000-0000-0000-000000000000")).status_code == 404
    assert (await alice.get("/projects/not-a-uuid")).status_code == 422


async def test_api_key_is_shown_once_and_stored_hashed(sign_up: SignUp, db: AsyncSession) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = await new_key(alice, project["id"])
    key = created["key"]
    assert key.startswith("ap_") and created["last4"] == key[-4:]
    listed = (await alice.get(f"/projects/{project['id']}/api-keys")).json()
    assert [k["id"] for k in listed] == [created["id"]]
    assert "key" not in listed[0] and "key_hash" not in listed[0]
    stored = await db.scalar(select(ApiKey).where(ApiKey.id == created["id"]))
    assert stored is not None and stored.key_hash == sha256(key) and key not in stored.key_hash


async def test_api_key_authenticates_and_records_use(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = await new_key(alice, project["id"])
    assert created["last_used_at"] is None
    r = await keyed(clients, created["key"]).get(f"/projects/{project['id']}")
    assert r.status_code == 200
    [listed] = (await alice.get(f"/projects/{project['id']}/api-keys")).json()
    assert listed["last_used_at"] is not None


async def test_api_key_is_scoped_to_its_project(sign_up: SignUp, clients: ClientFactory) -> None:
    alice = await sign_up("alice@example.com")
    mine = await new_project(alice, "a")
    other = await new_project(alice, "b")
    client = keyed(clients, (await new_key(alice, mine["id"]))["key"])
    assert [p["id"] for p in (await client.get("/projects")).json()] == [mine["id"]]
    assert (await client.get(f"/projects/{other['id']}")).status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/projects", {"name": "x"}),
        ("GET", "/projects/{id}/api-keys", None),
        ("POST", "/projects/{id}/api-keys", {"label": "x"}),
        ("DELETE", "/projects/{id}/api-keys/{key_id}", None),
    ],
)
async def test_api_keys_cannot_manage_account(
    sign_up: SignUp, clients: ClientFactory, method: str, path: str, body: dict[str, str] | None
) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = await new_key(alice, project["id"])
    url = path.format(id=project["id"], key_id=created["id"])
    r = await keyed(clients, created["key"]).request(method, url, json=body)
    assert r.status_code == 403


async def test_revoked_key_is_rejected(sign_up: SignUp, clients: ClientFactory) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = await new_key(alice, project["id"])
    url = f"/projects/{project['id']}/api-keys/{created['id']}"
    assert (await alice.delete(url)).status_code == 204
    assert (await alice.delete(url)).status_code == 204  # idempotent
    r = await keyed(clients, created["key"]).get("/projects")
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid or revoked API key"
    [listed] = (await alice.get(f"/projects/{project['id']}/api-keys")).json()
    assert listed["revoked_at"] is not None


async def test_unknown_key_is_rejected(clients: ClientFactory) -> None:
    r = await keyed(clients, "ap_" + "x" * 43).get("/projects")
    assert r.status_code == 401


async def test_api_keys_are_rate_limited(db: AsyncSession) -> None:
    app = bind_db(create_app(make_settings(rate_limit_per_minute=2)), db)
    async with client_for(app) as alice:
        await signed_up(alice, "alice@example.com")
        project = await new_project(alice)
        first, second = (
            (await new_key(alice, project["id"]))["key"],
            (await new_key(alice, project["id"]))["key"],
        )
        async with (
            client_for(app, headers={"Authorization": f"Bearer {first}"}) as a,
            client_for(app, headers={"Authorization": f"Bearer {second}"}) as b,
        ):
            assert [(await a.get("/projects")).status_code for _ in range(2)] == [200, 200]
            limited = await a.get("/projects")
            assert limited.status_code == 429
            assert int(limited.headers["retry-after"]) >= 1
            assert (await b.get("/projects")).status_code == 200  # per key, not global
        assert (await alice.get("/projects")).status_code == 200  # sessions aren't key-limited
