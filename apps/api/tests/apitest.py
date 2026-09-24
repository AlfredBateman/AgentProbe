"""Helpers shared by API tests (importable: apps/api/tests is on pytest's pythonpath)."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.db import get_db
from agentprobe_api.settings import Settings

WEB_ORIGIN = "https://web.test"
PASSWORD = "correct horse battery staple"  # fake credential
ALLOWED = ("alice@example.com", "bob@example.com", "carol@example.com")


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "jwt_secret": SecretStr("test-secret-" + "x" * 40),
        "signup_allowed_emails": ",".join(ALLOWED),
        "web_origin": WEB_ORIGIN,
        "cookie_secure": True,
        "rate_limit_backend": "memory",
        "rate_limit_per_minute": 10_000,
        "auth_rate_limit_per_minute": 10_000,
        **overrides,
    }
    return Settings(**values)


ClientFactory = Callable[..., httpx.AsyncClient]


def client_for(app: FastAPI, *, ip: str = "127.0.0.1", **kwargs: Any) -> httpx.AsyncClient:
    """A browser-like client: own cookie jar, https (Secure cookies), the web app's Origin."""
    transport = httpx.ASGITransport(app=app, client=(ip, 50000))
    headers = {"Origin": WEB_ORIGIN, **kwargs.pop("headers", {})}
    return httpx.AsyncClient(
        transport=transport, base_url="https://api.test", headers=headers, **kwargs
    )


def bind_db(app: FastAPI, db: AsyncSession) -> FastAPI:
    """Route the app's per-request sessions to the test transaction."""

    async def test_db() -> AsyncIterator[AsyncSession]:
        try:
            yield db
            await db.commit()  # releases a savepoint; the outer transaction still rolls back
        except Exception:
            await db.rollback()
            raise
        finally:
            db.expunge_all()  # each request starts with an empty identity map, as in prod

    app.dependency_overrides[get_db] = test_db
    return app


async def signed_up(client: httpx.AsyncClient, email: str) -> httpx.AsyncClient:
    r = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return client


SignUp = Callable[[str], Awaitable[httpx.AsyncClient]]
