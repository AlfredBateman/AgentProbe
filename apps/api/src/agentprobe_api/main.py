import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from agentprobe_api import auth, projects
from agentprobe_api.db import make_engine
from agentprobe_api.errors import error_response, install_error_handlers
from agentprobe_api.logs import configure_logging, redact_query, request_id_var
from agentprobe_api.ratelimit import MemoryTokenBucket, RateLimiter, RedisTokenBucket
from agentprobe_api.settings import Settings, get_settings

log = logging.getLogger("agentprobe")
access_log = logging.getLogger("agentprobe.access")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    """Request IDs, one access-log line per request, and 500s for unhandled errors.

    Pure ASGI (not BaseHTTPMiddleware) so streaming responses (SSE) aren't buffered. It turns
    unhandled exceptions into the standard error body itself, because Starlette's own
    Exception handler runs outside this middleware and would lose the request ID.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status: int | None = None

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [*message.get("headers", []), (b"x-request-id", request_id.encode())]
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            log.exception("unhandled error")
            if status is not None:
                raise  # response already started; nothing sane left to send
            await error_response(500, "internal_error", "Internal server error")(
                scope, receive, send_with_id
            )
        finally:
            access_log.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    # Redacted: the SSE fallback carries a stream token in the query (ADR 0009).
                    "query": redact_query(scope["query_string"].decode("latin-1")),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "client": (scope.get("client") or ("", 0))[0],
                },
            )
            request_id_var.reset(token)


def _limiter(redis: Redis | None, per_minute: int, prefix: str) -> RateLimiter:
    if redis is not None:
        return RedisTokenBucket(redis, per_minute, prefix=prefix)
    return MemoryTokenBucket(per_minute)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Fail at startup, not on the first login. Only the real server runs this; tests
        # drive the app through ASGITransport and override get_db instead.
        configure_logging(settings.log_level)
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        if settings.jwt_secret is None or len(settings.jwt_secret.get_secret_value()) < 32:
            raise RuntimeError("JWT_SECRET must be set to at least 32 characters")
        engine = make_engine(settings.database_url)
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        yield
        await engine.dispose()
        if redis is not None:
            await redis.aclose()

    app = FastAPI(title="AgentProbe API", lifespan=lifespan)
    app.state.settings = settings
    redis = Redis.from_url(settings.redis_url) if settings.rate_limit_backend == "redis" else None
    app.state.api_key_limiter = _limiter(redis, settings.rate_limit_per_minute, "rl:key:")
    app.state.auth_limiter = _limiter(redis, settings.auth_rate_limit_per_minute, "rl:ip:")
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(projects.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
