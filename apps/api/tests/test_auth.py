import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.main import create_app
from agentprobe_api.models import RefreshToken, User
from agentprobe_api.security import encode_token, sha256
from apitest import PASSWORD, ClientFactory, SignUp, bind_db, client_for, make_settings

pytestmark = pytest.mark.integration
SECRET = make_settings().jwt_secret
assert SECRET is not None


def set_cookies(r: httpx.Response) -> dict[str, str]:
    return {c.split("=", 1)[0]: c for c in r.headers.get_list("set-cookie")}


# --- register / login ---------------------------------------------------------------------


async def test_register_sets_hardened_session_cookies(
    clients: ClientFactory, db: AsyncSession
) -> None:
    r = await clients().post(
        "/auth/register", json={"email": "Alice@Example.com", "password": PASSWORD}
    )
    assert r.status_code == 201
    assert r.json()["email"] == "alice@example.com"  # normalised
    cookies = set_cookies(r)
    for name, samesite in (("access_token", "lax"), ("refresh_token", "strict")):
        attrs = cookies[name].lower()
        assert "httponly" in attrs and "secure" in attrs and f"samesite={samesite}" in attrs
    user = await db.scalar(select(User).where(User.email == "alice@example.com"))
    assert user is not None and user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


async def test_register_rejects_emails_not_on_allowlist(clients: ClientFactory) -> None:
    r = await clients().post(
        "/auth/register", json={"email": "mallory@example.com", "password": PASSWORD}
    )
    assert r.status_code == 403
    assert "access_token" not in set_cookies(r)


async def test_register_rejects_duplicate_email(sign_up: SignUp, clients: ClientFactory) -> None:
    await sign_up("alice@example.com")
    r = await clients().post(
        "/auth/register", json={"email": "ALICE@example.com", "password": PASSWORD}
    )
    assert r.status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "alice@example.com", "password": "too-short"},
        {"email": "alice@example.com", "password": "x" * 129},
    ],
)
async def test_register_validates_input(clients: ClientFactory, body: dict[str, str]) -> None:
    assert (await clients().post("/auth/register", json=body)).status_code == 422


async def test_login_succeeds_and_session_works(sign_up: SignUp, clients: ClientFactory) -> None:
    await sign_up("alice@example.com")
    client = clients()
    r = await client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert (await client.get("/projects")).status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [("alice@example.com", "wrong password!!"), ("nobody@example.com", PASSWORD)],
)
async def test_login_failures_are_indistinguishable(
    sign_up: SignUp, clients: ClientFactory, email: str, password: str
) -> None:
    await sign_up("alice@example.com")
    r = await clients().post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid email or password"


async def test_auth_endpoints_are_rate_limited_per_ip(db: AsyncSession) -> None:
    app = bind_db(create_app(make_settings(auth_rate_limit_per_minute=2)), db)
    body = {"email": "alice@example.com", "password": "wrong password!!"}
    async with client_for(app, ip="203.0.113.7") as a, client_for(app, ip="203.0.113.8") as b:
        assert [(await a.post("/auth/login", json=body)).status_code for _ in range(2)] == [
            401,
            401,
        ]
        limited = await a.post("/auth/login", json=body)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert int(limited.headers["retry-after"]) >= 1
        assert (await a.post("/auth/register", json=body)).status_code == 429  # shared budget
        assert (await b.post("/auth/login", json=body)).status_code == 401  # other IP unaffected


# --- access tokens ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "garbage",
        encode_token(SECRET, "access", uuid.uuid4(), timedelta(seconds=-5)),  # expired
        encode_token(SECRET, "stream", uuid.uuid4(), timedelta(minutes=1)),  # wrong type
        encode_token(
            make_settings(jwt_secret="another-secret-" + "q" * 40).jwt_secret,  # type: ignore[arg-type]
            "access",
            uuid.uuid4(),
            timedelta(minutes=1),
        ),  # forged
    ],
    ids=["garbage", "expired", "stream-token", "wrong-signature"],
)
async def test_invalid_access_tokens_are_rejected(clients: ClientFactory, token: str) -> None:
    r = await clients(headers={"Cookie": f"access_token={token}"}).get("/projects")
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid or expired session"


# --- refresh / logout ---------------------------------------------------------------------


async def test_refresh_rotates_tokens(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    old = alice.cookies["refresh_token"]
    r = await alice.post("/auth/refresh")
    assert r.status_code == 204
    assert alice.cookies["refresh_token"] != old
    assert (await alice.get("/projects")).status_code == 200


async def test_refresh_token_reuse_revokes_every_session(
    sign_up: SignUp, clients: ClientFactory, db: AsyncSession
) -> None:
    alice = await sign_up("alice@example.com")
    stolen = alice.cookies["refresh_token"]
    assert (await alice.post("/auth/refresh")).status_code == 204  # legit rotation
    replay = await clients(headers={"Cookie": f"refresh_token={stolen}"}).post("/auth/refresh")
    assert replay.status_code == 401
    assert "reuse" in replay.json()["error"]["message"]
    assert (await alice.post("/auth/refresh")).status_code == 401  # rotated token died too
    active = await db.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
    assert list(active) == []


async def test_expired_refresh_token_is_rejected(sign_up: SignUp, db: AsyncSession) -> None:
    alice = await sign_up("alice@example.com")
    token = await db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == sha256(alice.cookies["refresh_token"])
        )
    )
    assert token is not None
    token.expires_at = token.created_at - timedelta(seconds=1)
    await db.commit()
    r = await alice.post("/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Session expired"


async def test_logout_revokes_refresh_token_and_clears_cookies(
    sign_up: SignUp, clients: ClientFactory
) -> None:
    alice = await sign_up("alice@example.com")
    refresh = alice.cookies["refresh_token"]
    r = await alice.post("/auth/logout")
    assert r.status_code == 204
    assert "access_token" not in alice.cookies and "refresh_token" not in alice.cookies
    replay = await clients(headers={"Cookie": f"refresh_token={refresh}"}).post("/auth/refresh")
    assert replay.status_code == 401


# --- CSRF ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/projects", {"name": "p"}),
        ("POST", "/auth/refresh", None),
        ("POST", "/auth/logout", None),
    ],
)
async def test_cookie_mutations_require_web_origin(
    sign_up: SignUp, method: str, path: str, body: dict[str, str] | None
) -> None:
    alice = await sign_up("alice@example.com")
    for origin in ("https://evil.test", ""):
        r = await alice.request(method, path, json=body, headers={"Origin": origin})
        assert r.status_code == 403, (origin, r.text)
    assert (
        await alice.get("/projects", headers={"Origin": "https://evil.test"})
    ).status_code == 200
