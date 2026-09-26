"""POST/DELETE /runs/{id}/share and the public GET /shared/{token} (ADR 0018)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.models import Run
from apitest import ClientFactory, SignUp
from runtest import SMOKE_YAML, make_project, start_run, wait_for_run

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]


async def a_completed_run(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> tuple[httpx.AsyncClient, dict[str, str], dict[str, Any]]:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    return alice, ids, done


async def test_share_link_gives_a_sanitized_read_only_view(
    sign_up: SignUp, app: FastAPI, demo_url: str, clients: ClientFactory
) -> None:
    alice, ids, done = await a_completed_run(sign_up, app, demo_url)

    r = await alice.post(f"/runs/{done['id']}/share", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["expires_at"] is None
    assert body["url"] is None  # PUBLIC_WEB_URL isn't configured in tests
    token = body["token"]

    anonymous = clients(headers={"Origin": "https://elsewhere.test"})
    shared = await anonymous.get(f"/shared/{token}")
    assert shared.status_code == 200, shared.text
    view = shared.json()
    assert view["suite"] == "smoke"
    assert view["agent"] == "support-v1"
    assert view["status"] == "completed"
    assert len(view["cases"]) == 8
    assert len(view["results"]) == 40
    assert all("output" in r for r in view["results"])
    # Sanitized: no agent config, secrets or internal ids anywhere in the payload.
    dumped = str(view)
    assert demo_url not in dumped  # no URL leaked from the agent config
    assert str(ids["agent_id"]) not in dumped
    assert str(ids["suite_id"]) not in dumped
    assert str(done["id"]) not in dumped


async def test_a_missing_or_random_token_is_404(clients: ClientFactory) -> None:
    anonymous = clients()
    r = await anonymous.get(f"/shared/{uuid.uuid4().hex}")
    assert r.status_code == 404


async def test_revoke_invalidates_the_link(
    sign_up: SignUp, app: FastAPI, demo_url: str, clients: ClientFactory
) -> None:
    alice, _, done = await a_completed_run(sign_up, app, demo_url)
    token = (await alice.post(f"/runs/{done['id']}/share", json={})).json()["token"]
    anonymous = clients()
    assert (await anonymous.get(f"/shared/{token}")).status_code == 200

    revoked = await alice.delete(f"/runs/{done['id']}/share")
    assert revoked.status_code == 204
    assert (await anonymous.get(f"/shared/{token}")).status_code == 404
    # Idempotent: revoking again (already gone) doesn't error.
    assert (await alice.delete(f"/runs/{done['id']}/share")).status_code == 204


async def test_expiry_is_honored(
    sign_up: SignUp, app: FastAPI, demo_url: str, clients: ClientFactory, db: AsyncSession
) -> None:
    alice, _, done = await a_completed_run(sign_up, app, demo_url)
    r = await alice.post(f"/runs/{done['id']}/share", json={"expires_in_days": 1})
    assert r.status_code == 201
    body = r.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=23) < expires_at - datetime.now(UTC) <= timedelta(days=1)
    token = body["token"]
    anonymous = clients()
    assert (await anonymous.get(f"/shared/{token}")).status_code == 200

    # A day later (moved back rather than waiting): the link is dead.
    await db.execute(
        update(Run)
        .where(Run.id == uuid.UUID(done["id"]))
        .values(share_expires_at=func.now() - timedelta(seconds=1))
    )
    assert (await anonymous.get(f"/shared/{token}")).status_code == 404


async def test_only_the_owner_can_create_or_revoke_a_share(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    _, _, done = await a_completed_run(sign_up, app, demo_url)
    bob = await sign_up("bob@example.com")
    assert (await bob.post(f"/runs/{done['id']}/share", json={})).status_code == 404
    assert (await bob.delete(f"/runs/{done['id']}/share")).status_code == 404
