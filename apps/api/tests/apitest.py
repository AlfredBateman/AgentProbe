"""Helpers shared by API tests (importable: apps/api/tests is on pytest's pythonpath)."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from cryptography.fernet import Fernet
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
        "encryption_key": SecretStr(Fernet.generate_key().decode()),
        "signup_allowed_emails": ",".join(ALLOWED),
        "web_origin": WEB_ORIGIN,
        "cookie_secure": True,
        "rate_limit_backend": "memory",
        "rate_limit_per_minute": 10_000,
        "auth_rate_limit_per_minute": 10_000,
        # A developer's own .env may set PUBLIC_WEB_URL; pin it so tests never depend on
        # what happens to be in the environment they run in. Pass it explicitly to test it.
        "public_web_url": None,
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


class SharedSessions:
    """Background work's sessions in tests (ADR 0008 amendment): every `sessions()` is the
    test's own session, so what runs and workers write still rolls back with the test.
    One user at a time: requests (`bind_db`) and background work take the same lock.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[AsyncSession]:
        async with self.lock:
            try:
                yield self.db
            finally:
                await self.db.rollback()  # like closing a real session: uncommitted work is lost
                self.db.expunge_all()


def bind_db(app: FastAPI, db: AsyncSession) -> FastAPI:
    """Route the app's per-request sessions, and its background work, to the test transaction."""
    shared = SharedSessions(db)
    app.state.sessionmaker = shared

    async def test_db() -> AsyncIterator[AsyncSession]:
        async with shared.lock:
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
