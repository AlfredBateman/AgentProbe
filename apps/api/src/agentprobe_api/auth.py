"""Sessions, login, and the one auth dependency for users and API keys (ADR 0009)."""

import asyncio
import hmac
import ipaddress
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import limits
from agentprobe_api.db import get_db
from agentprobe_api.errors import ApiError
from agentprobe_api.models import ApiKey, Project, RefreshToken, User
from agentprobe_api.ratelimit import RateLimiter, retry_after_header
from agentprobe_api.security import (
    API_KEY_PREFIX,
    InvalidToken,
    decode_token,
    encode_token,
    hash_password,
    needs_rehash,
    new_refresh_token,
    sha256,
    verify_password,
)
from agentprobe_api.settings import Settings

log = logging.getLogger("agentprobe.auth")
ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

Db = Annotated[AsyncSession, Depends(get_db, scope="function")]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


AppSettings = Annotated[Settings, Depends(get_settings)]


def _jwt_secret(settings: Settings) -> SecretStr:
    if settings.jwt_secret is None:
        raise RuntimeError("JWT_SECRET is not set")
    return settings.jwt_secret


async def _limit(limiter: RateLimiter, bucket: str) -> None:
    if (retry := await limiter.acquire(bucket)) is not None:
        raise ApiError(429, "Too many requests", headers={"Retry-After": retry_after_header(retry)})


def _origin_of(url: str | None) -> str | None:
    """scheme://host of a URL: a Referer's path and query can carry tokens."""
    parts = urlsplit(url or "")
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else None


def _check_origin(request: Request, settings: Settings) -> None:
    """CSRF defence for cookie-authenticated mutations, on top of SameSite (ADR 0009)."""
    origin = request.headers.get("origin")
    if request.method in _SAFE_METHODS or origin == settings.web_origin:
        return
    # What a 403 needs to be diagnosed from the logs (ADR 0036): never cookies or secrets.
    log.warning(
        "cross-origin request rejected",
        extra={
            "reason": "origin missing" if origin is None else "origin != WEB_ORIGIN",
            "origin": origin,
            "web_origin": settings.web_origin,
            "method": request.method,
            "path": request.url.path,
            "sec_fetch_site": request.headers.get("sec-fetch-site"),
            "referer_origin": _origin_of(request.headers.get("referer")),
        },
    )
    raise ApiError(403, "Cross-origin request rejected")


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    project_id: uuid.UUID | None = None  # set when authenticated by a project API key
    api_key_id: uuid.UUID | None = None

    @property
    def is_api_key(self) -> bool:
        return self.api_key_id is not None


async def get_principal(request: Request, db: Db, settings: AppSettings) -> Principal:
    """A user (access-token cookie) or a project API key (`Authorization: Bearer ap_…`)."""
    header = request.headers.get("authorization")
    if header is not None:
        scheme, _, credential = header.partition(" ")
        if scheme.lower() != "bearer" or not credential.startswith(API_KEY_PREFIX):
            raise _unauthenticated("Authorization header must be `Bearer ap_…`")
        return await _api_key_principal(request, db, credential)

    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise _unauthenticated("Not authenticated")
    _check_origin(request, settings)
    try:
        claims = decode_token(_jwt_secret(settings), "access", token)
    except InvalidToken:
        raise _unauthenticated("Invalid or expired session") from None
    return Principal(user_id=uuid.UUID(claims["sub"]))


async def _api_key_principal(request: Request, db: AsyncSession, key: str) -> Principal:
    # One round trip: find the live key, record the use, and return its scope.
    # ponytail: one UPDATE per keyed request; throttle to once a minute if traffic grows.
    row = (
        await db.execute(
            update(ApiKey)
            .where(
                ApiKey.key_hash == sha256(key),
                ApiKey.revoked_at.is_(None),
                Project.id == ApiKey.project_id,
            )
            .values(last_used_at=func.now())
            .returning(ApiKey.id, ApiKey.project_id, Project.user_id)
        )
    ).first()
    if row is None:  # unknown and revoked look the same
        raise _unauthenticated("Invalid or revoked API key")
    await _limit(request.app.state.api_key_limiter, f"key:{row.id}")
    return Principal(user_id=row.user_id, project_id=row.project_id, api_key_id=row.id)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_user(principal: CurrentPrincipal) -> Principal:
    """For account-level actions an API key must never perform (projects, key management)."""
    if principal.is_api_key:
        raise ApiError(403, "This action requires a user session, not an API key")
    return principal


CurrentUser = Annotated[Principal, Depends(require_user)]


def require_api_key(principal: CurrentPrincipal) -> Principal:
    """For CI-facing actions (`/ci/report`) that a browser session must never reach."""
    if not principal.is_api_key:
        raise ApiError(403, "This action requires a project API key, not a user session")
    return principal


CurrentApiKey = Annotated[Principal, Depends(require_api_key)]


def _unauthenticated(message: str) -> ApiError:
    return ApiError(401, message, headers={"WWW-Authenticate": "Bearer"})


STREAM_TOKEN_TTL = timedelta(seconds=60)


def mint_stream_token(settings: Settings, user_id: uuid.UUID, run_id: uuid.UUID) -> str:
    """The SSE fallback's query token (ADR 0009 §5): one run, one user, 60 seconds."""
    return encode_token(
        _jwt_secret(settings), "stream", user_id, STREAM_TOKEN_TTL, run_id=str(run_id)
    )


def stream_principal(settings: Settings, token: str, run_id: uuid.UUID) -> Principal:
    """The user a stream token was minted for, valid only on that run's stream."""
    try:
        claims = decode_token(_jwt_secret(settings), "stream", token)
    except InvalidToken:
        raise _unauthenticated("Invalid or expired stream token") from None
    if claims.get("run_id") != str(run_id):
        raise _unauthenticated("This stream token is for another run")
    return Principal(user_id=uuid.UUID(claims["sub"]))


# --- routes ---------------------------------------------------------------------------

router = APIRouter(prefix="/auth", tags=["auth"])


class Registration(BaseModel):
    email: EmailStr
    # NIST 800-63B: length over composition rules. The max bounds argon2 work per request.
    password: str = Field(min_length=12, max_length=128)


class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)  # no policy: accounts may predate it


class UserOut(BaseModel):
    id: uuid.UUID
    email: str


PROXY_SECRET_HEADER = "x-agentprobe-proxy-secret"  # noqa: S105  a header name


def client_ip(request: Request, settings: Settings) -> str:
    """The IP that per-IP rate limits key on (ADR 0036).

    The web app's server-side proxy replaces X-Forwarded-For with exactly the browser's
    address and adds PROXY_SECRET. The hops after it (Vercel's rewrite, Render's edge) only
    append, so on a request with the right secret the leftmost entry is the browser. Without
    the secret X-Forwarded-For is text the caller chose, so it keys on the connecting address
    (uvicorn rewrites that from X-Forwarded-For only for its own FORWARDED_ALLOW_IPS peers:
    local and compose; on Render it's Render's proxy).
    """
    peer = request.client.host if request.client else "unknown"
    secret = settings.proxy_secret
    if secret is None or not hmac.compare_digest(
        request.headers.get(PROXY_SECRET_HEADER, "").encode(), secret.get_secret_value().encode()
    ):
        return peer
    leftmost = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(leftmost))
    except ValueError:
        return peer  # none or malformed: key on the proxy, never on header text


# Each argon2 hash or verify allocates 64 MiB (argon2-cffi's RFC 9106 low-memory profile), and
# the default thread pool would run a dozen at once: past a 512 MB service (ADR 0036).
ARGON2_SLOTS = 2


async def _argon2[T](request: Request, fn: Callable[..., T], *args: object) -> T:
    """argon2 off the event loop, at most ARGON2_SLOTS at a time."""
    async with request.app.state.argon2_slots:
        return await asyncio.to_thread(fn, *args)


async def _start_session(
    db: AsyncSession, response: Response, settings: Settings, user_id: uuid.UUID
) -> None:
    refresh = new_refresh_token()
    ttl = timedelta(days=settings.refresh_ttl_days)
    db.add(
        RefreshToken(
            user_id=user_id, token_hash=sha256(refresh), expires_at=datetime.now(UTC) + ttl
        )
    )
    access_ttl = timedelta(minutes=settings.jwt_ttl_minutes)
    access = encode_token(_jwt_secret(settings), "access", user_id, access_ttl)
    for name, value, max_age, samesite in (
        (ACCESS_COOKIE, access, access_ttl, "lax"),
        (REFRESH_COOKIE, refresh, ttl, "strict"),
    ):
        response.set_cookie(
            name,
            value,
            max_age=int(max_age.total_seconds()),
            httponly=True,
            secure=settings.cookie_secure,
            samesite=samesite,  # type: ignore[arg-type]
            path="/",
        )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", secure=settings.cookie_secure, httponly=True)


@router.post("/register", status_code=201)
async def register(
    body: Registration, request: Request, response: Response, db: Db, settings: AppSettings
) -> UserOut:
    _check_origin(request, settings)  # login CSRF matters once signup is open (ADR 0035)
    ip = client_ip(request, settings)
    await _limit(request.app.state.auth_limiter, f"ip:{ip}")
    await _limit(request.app.state.register_limiter, f"ip:{ip}")
    email = body.email.lower()
    if not settings.signup_open and email not in settings.signup_allowlist:
        raise ApiError(403, "Registration is closed for this email")
    await limits.check_signups(db, settings)
    password_hash = await _argon2(request, hash_password, body.password)
    user_id = await db.scalar(  # one round trip; the unique index decides duplicates
        insert(User)
        .values(id=uuid.uuid4(), email=email, password_hash=password_hash)
        .on_conflict_do_nothing(index_elements=[User.email])
        .returning(User.id)
    )
    if user_id is None:
        raise ApiError(409, "An account with this email already exists")
    await _start_session(db, response, settings, user_id)
    return UserOut(id=user_id, email=email)


@router.post("/login")
async def login(
    body: Login, request: Request, response: Response, db: Db, settings: AppSettings
) -> UserOut:
    _check_origin(request, settings)
    await _limit(request.app.state.auth_limiter, f"ip:{client_ip(request, settings)}")
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    # verify first: an unknown email still pays for one argon2 verify (no timing oracle).
    stored = user.password_hash if user else None
    if not await _argon2(request, verify_password, stored, body.password) or user is None:
        raise _unauthenticated("Invalid email or password")
    if needs_rehash(user.password_hash):
        user.password_hash = await _argon2(request, hash_password, body.password)
    await _start_session(db, response, settings, user.id)
    return UserOut(id=user.id, email=user.email)


@router.get("/me")
async def me(user: CurrentUser, db: Db) -> UserOut:
    """The signed-in user. The web client also probes it to learn whether another tab has
    already refreshed the session, before it spends the refresh token (ADR 0029).
    """
    email = await db.scalar(select(User.email).where(User.id == user.user_id))
    if email is None:  # a valid access token for a deleted account
        raise _unauthenticated("Invalid or expired session")
    return UserOut(id=user.user_id, email=email)


@router.post("/refresh", status_code=204)
async def refresh(request: Request, response: Response, db: Db, settings: AppSettings) -> None:
    """Rotates the refresh token. Presenting an already-rotated token means it was stolen
    (or replayed), so every session of that user is revoked.
    """
    _check_origin(request, settings)
    raw = request.cookies.get(REFRESH_COOKIE, "")
    token = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw)))
    now = datetime.now(UTC)
    if not raw or token is None:
        raise _unauthenticated("Invalid session")
    if token.revoked_at is not None:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()  # the revocation must stick even though this request fails
        raise _unauthenticated("Session reuse detected; all sessions revoked")
    if token.expires_at <= now:
        raise _unauthenticated("Session expired")
    token.revoked_at = now
    await _start_session(db, response, settings, token.user_id)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: Db, settings: AppSettings) -> None:
    _check_origin(request, settings)
    if raw := request.cookies.get(REFRESH_COOKIE):
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == sha256(raw), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    _clear_session_cookies(response, settings)
