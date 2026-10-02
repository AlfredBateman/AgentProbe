"""Public-deploy caps and signup rules through the real endpoints (ADR 0035, ADR 0036)."""

from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.auth import CLIENT_IP_HEADER, PROXY_SECRET_HEADER
from agentprobe_api.main import create_app
from apitest import PASSWORD, bind_db, client_for, make_settings, signed_up
from runtest import SMALL_YAML, attempt, make_project

pytestmark = pytest.mark.integration
AGENT_URL = "http://127.0.0.1:9/chat"  # never called: nothing here executes a run


def app_with(db: AsyncSession, **overrides: Any) -> httpx.AsyncClient:
    return client_for(bind_db(create_app(make_settings(**overrides)), db))


async def register(client: httpx.AsyncClient, email: str, **headers: str) -> int:
    body = {"email": email, "password": PASSWORD}
    return (await client.post("/auth/register", json=body, headers=headers)).status_code


# --- signup ---------------------------------------------------------------------------------


async def test_open_signup_accepts_any_email_and_allowlist_mode_does_not(db: AsyncSession) -> None:
    async with app_with(db) as closed:
        assert await register(closed, "stranger@example.com") == 403
    async with app_with(db, signup_open=True) as open_:
        assert await register(open_, "stranger@example.com") == 201


async def test_registration_is_limited_per_ip_per_hour(db: AsyncSession) -> None:
    app = bind_db(create_app(make_settings(signup_open=True, register_rate_limit_per_hour=2)), db)
    async with client_for(app, ip="203.0.113.7") as a, client_for(app, ip="203.0.113.8") as b:
        assert [await register(a, f"u{n}@example.com") for n in range(3)] == [201, 201, 429]
        assert await register(b, "other@example.com") == 201  # another IP is unaffected


async def test_signups_per_day_cap_is_global(db: AsyncSession) -> None:
    app = bind_db(create_app(make_settings(signup_open=True, max_signups_per_day=1)), db)
    async with client_for(app, ip="203.0.113.7") as a, client_for(app, ip="203.0.113.8") as b:
        assert await register(a, "first@example.com") == 201
        assert await register(b, "second@example.com") == 429


async def test_the_web_proxy_secret_keys_limits_on_the_browser_ip(db: AsyncSession) -> None:
    # One TCP peer (the web proxy) carrying two browsers: with the secret each has its own
    # bucket; without it, a forged header changes nothing and they share the peer's.
    secret = "p" * 40
    app = bind_db(
        create_app(
            make_settings(
                signup_open=True, register_rate_limit_per_hour=1, proxy_secret=SecretStr(secret)
            )
        ),
        db,
    )
    async with client_for(app, ip="198.51.100.9") as proxy:
        trusted = {PROXY_SECRET_HEADER: secret}
        assert await register(proxy, "a@example.com", **trusted, **via_proxy("203.0.113.1")) == 201
        assert await register(proxy, "b@example.com", **trusted, **via_proxy("203.0.113.2")) == 201
        assert await register(proxy, "c@example.com", **via_proxy("203.0.113.3")) == 201
        assert await register(proxy, "d@example.com", **via_proxy("203.0.113.4")) == 429


def via_proxy(browser: str) -> dict[str, str]:
    """The web proxy's client-IP header, plus an X-Forwarded-For that must not matter: in
    production a browser's own entry could come first (ADR 0036)."""
    return {CLIENT_IP_HEADER: browser, "x-forwarded-for": f"198.51.100.66, {browser}, 10.0.0.7"}


# --- per-user caps ---------------------------------------------------------------------------


async def test_project_and_agent_caps(db: AsyncSession) -> None:
    async with app_with(db, max_projects_per_user=1, max_agents_per_user=1) as alice:
        await signed_up(alice, "alice@example.com")
        ids = await make_project(alice, AGENT_URL)
        r = await alice.post("/projects", json={"name": "second"})
        assert r.status_code == 403 and "Project limit" in r.json()["error"]["message"]
        agent = {"name": "another", "config": {"adapter_type": "http", "url": AGENT_URL}}
        r = await alice.post(f"/projects/{ids['project_id']}/agents", json=agent)
        assert r.status_code == 403 and "Agent limit" in r.json()["error"]["message"]


async def test_cases_per_suite_cap_applies_to_create_and_update(db: AsyncSession) -> None:
    async with app_with(db, max_cases_per_suite=1) as alice:
        await signed_up(alice, "alice@example.com")
        project = (await alice.post("/projects", json={"name": "p"})).json()
        r = await alice.post(f"/projects/{project['id']}/suites", json={"yaml": SMALL_YAML})
        assert r.status_code == 422  # SMALL_YAML has 2 cases
        one_case = SMALL_YAML.split("  - id: refund-outside-window")[0]
        suite = await alice.post(f"/projects/{project['id']}/suites", json={"yaml": one_case})
        assert suite.status_code == 201, suite.text
        r = await alice.put(f"/suites/{suite.json()['id']}", json={"yaml": SMALL_YAML})
        assert r.status_code == 422


async def ci_client(
    alice: httpx.AsyncClient, project_id: str, db: AsyncSession, **overrides: Any
) -> httpx.AsyncClient:
    key = (await alice.post(f"/projects/{project_id}/api-keys", json={"label": "ci"})).json()["key"]
    client = app_with(db, **overrides)
    client.headers["Authorization"] = f"Bearer {key}"
    return client


def report(*, mock: bool = True) -> dict[str, Any]:
    results = [
        attempt(case, n, passed=True)
        for case in ("greeting", "refund-outside-window")
        for n in range(2)
    ]
    return {
        "suite": "small",
        "agent": "support-v1",
        "branch": "main",
        "results": results,
        "mock": mock,
    }


async def test_runs_per_day_cap_counts_ci_reports_and_server_runs(db: AsyncSession) -> None:
    caps = {"max_runs_per_user_per_day": 1}
    async with app_with(db, **caps) as alice:
        await signed_up(alice, "alice@example.com")
        ids = await make_project(alice, AGENT_URL)
        async with await ci_client(alice, ids["project_id"], db, **caps) as ci:
            first = await ci.post("/ci/report", json=report())
            assert first.status_code == 201, first.text
            second = await ci.post("/ci/report", json=report())
            assert second.status_code == 429, second.text
        r = await alice.post(f"/suites/{ids['suite_id']}/runs", json={})
        assert r.status_code == 429 and "Daily run limit" in r.json()["error"]["message"]


async def test_live_budget_reserves_twice_the_per_run_cap(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Live is configured but RUN_LIVE is not set, so nothing could reach a provider anyway.
    monkeypatch.setenv("LLM_PROVIDER", "litellm")
    monkeypatch.delenv("RUN_LIVE", raising=False)
    monkeypatch.setenv("LLM_BUDGET_USD_PER_RUN", "0.25")  # each live run reserves $0.50
    caps = {"llm_global_usd_per_day": 1.0}
    async with app_with(db, **caps) as alice:
        await signed_up(alice, "alice@example.com")
        ids = await make_project(alice, AGENT_URL)
        async with await ci_client(alice, ids["project_id"], db, **caps) as ci:
            statuses = [
                (await ci.post("/ci/report", json=report(mock=False))).status_code for _ in range(3)
            ]
            assert statuses == [201, 201, 429]
            assert (await ci.post("/ci/report", json=report(mock=True))).status_code == 201
        r = await alice.post(f"/suites/{ids['suite_id']}/runs", json={"mock": False})
        assert r.status_code == 429 and "live-LLM budget" in r.json()["error"]["message"]
