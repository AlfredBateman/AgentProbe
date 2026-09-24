from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from agentprobe_api.settings import get_settings

# Neon cold-starts a suspended compute in a few seconds; fail after 10 rather than hang.
CONNECT_ARGS = {"connect_timeout": 10}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def normalize_url(url: str) -> str:
    """Accept the `postgresql://` string Neon gives you and target psycopg 3.

    Remote hosts without an explicit sslmode get `sslmode=require`. Neon's own
    `sslmode`/`channel_binding` params pass through to libpq untouched.
    """
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+psycopg"
    elif scheme != "postgresql+psycopg":
        raise ValueError(f"Unsupported database URL scheme: {parts.scheme!r}")
    query = parse_qsl(parts.query)
    if parts.hostname not in _LOCAL_HOSTS and not any(k == "sslmode" for k, _ in query):
        query.append(("sslmode", "require"))
    return urlunsplit(parts._replace(scheme=scheme, query=urlencode(query)))


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request, committed when the endpoint returns without raising.

    Use as Depends(get_db, scope="function") so the commit happens before the response is
    sent, and a failed commit becomes a 500 instead of a silently lost write.
    """
    async with request.app.state.sessionmaker() as session:
        yield session
        await session.commit()


def make_engine(url: str | None = None) -> AsyncEngine:
    url = url or get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_async_engine(
        normalize_url(url),
        pool_pre_ping=True,  # a Neon compute that suspended has closed our pooled sockets
        pool_recycle=300,  # Neon suspends after ~5 min idle
        connect_args=CONNECT_ARGS,
    )
