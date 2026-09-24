import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.models import Secret
from apitest import SignUp

pytestmark = pytest.mark.integration

HTTP_CONFIG = {
    "adapter_type": "http",
    "url": "https://agent.example.com/chat",
}


async def new_project(client: httpx.AsyncClient, name: str = "demo") -> dict[str, str]:
    r = await client.post("/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_create_and_get_http_agent(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    r = await alice.post(
        f"/projects/{project['id']}/agents", json={"name": "support-bot", "config": HTTP_CONFIG}
    )
    assert r.status_code == 201, r.text
    agent = r.json()
    assert agent["adapter_type"] == "http"
    assert agent["has_secret"] is False
    assert agent["config"]["url"] == HTTP_CONFIG["url"]
    got = await alice.get(f"/agents/{agent['id']}")
    assert got.status_code == 200
    assert got.json() == agent


async def test_auth_header_is_encrypted_and_never_returned(
    sign_up: SignUp, db: AsyncSession
) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    r = await alice.post(
        f"/projects/{project['id']}/agents",
        json={
            "name": "support-bot",
            "config": HTTP_CONFIG,
            "auth_header": {"name": "Authorization", "value": "Bearer super-secret"},
        },
    )
    assert r.status_code == 201, r.text
    agent = r.json()
    assert agent["has_secret"] is True
    assert "auth_header" not in agent
    body_text = r.text
    assert "super-secret" not in body_text
    secret = await db.scalar(select(Secret))
    assert secret is not None
    assert b"super-secret" not in secret.ciphertext


async def test_python_adapter_rejected(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    r = await alice.post(
        f"/projects/{project['id']}/agents",
        json={
            "name": "cli-bot",
            "config": {"adapter_type": "python", "module": "demo", "function": "run"},
        },
    )
    assert r.status_code == 400, r.text


async def test_invalid_http_config_rejected(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    r = await alice.post(
        f"/projects/{project['id']}/agents",
        json={"name": "bad", "config": {"adapter_type": "http"}},  # missing url
    )
    assert r.status_code == 422


async def test_duplicate_agent_name_rejected(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    body = {"name": "support-bot", "config": HTTP_CONFIG}
    assert (await alice.post(f"/projects/{project['id']}/agents", json=body)).status_code == 201
    r = await alice.post(f"/projects/{project['id']}/agents", json=body)
    assert r.status_code == 409


async def test_list_agents(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    for name in ("a", "b"):
        await alice.post(
            f"/projects/{project['id']}/agents", json={"name": name, "config": HTTP_CONFIG}
        )
    r = await alice.get(f"/projects/{project['id']}/agents")
    assert r.status_code == 200
    assert [a["name"] for a in r.json()] == ["a", "b"]


async def test_update_agent_name_config_and_secret(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = (
        await alice.post(
            f"/projects/{project['id']}/agents", json={"name": "bot", "config": HTTP_CONFIG}
        )
    ).json()
    r = await alice.put(
        f"/agents/{created['id']}",
        json={
            "name": "renamed-bot",
            "config": {"adapter_type": "http", "url": "https://new.example.com"},
            "auth_header": {"name": "X-Api-Key", "value": "k"},
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["name"] == "renamed-bot"
    assert updated["config"]["url"] == "https://new.example.com/"  # pydantic adds the root path
    assert updated["has_secret"] is True

    cleared = await alice.put(f"/agents/{created['id']}", json={"clear_secret": True})
    assert cleared.status_code == 200
    assert cleared.json()["has_secret"] is False


async def test_update_rejects_python_adapter(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = (
        await alice.post(
            f"/projects/{project['id']}/agents", json={"name": "bot", "config": HTTP_CONFIG}
        )
    ).json()
    r = await alice.put(
        f"/agents/{created['id']}",
        json={"config": {"adapter_type": "python", "module": "m", "function": "f"}},
    )
    assert r.status_code == 400


async def test_delete_agent(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = (
        await alice.post(
            f"/projects/{project['id']}/agents", json={"name": "bot", "config": HTTP_CONFIG}
        )
    ).json()
    assert (await alice.delete(f"/agents/{created['id']}")).status_code == 204
    assert (await alice.get(f"/agents/{created['id']}")).status_code == 404


async def test_get_nonexistent_agent_is_404(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.get("/agents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
