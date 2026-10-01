"""One FastAPI app, one process, one port: serves every bundled demo agent under a path
prefix. See README.md for the route list and the deliberately-vulnerable warning.
"""

import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager

import uvicorn
from fastapi import FastAPI, Request, Response

from agentprobe_demo_agents import routes_rag, routes_support, routes_vulnerable
from agentprobe_demo_agents.mcp_server import MCP_ROUTE, build_mcp_server

# On every response, so the public deployed copy is labelled wherever it's reached from
# (ADR 0036).
WARNING = "Deliberately vulnerable demo with planted flaws. No real data: fake data only."


def create_app() -> FastAPI:
    # A fresh MCPServer per app: its session_manager can only be run() once, and create_app()
    # itself is re-callable (each test module's own server, `agentprobe-demo-agents`'s module
    # singleton below), so a shared instance would fail the second server's lifespan startup.
    mcp_tools = build_mcp_server()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # streamable_http_app() wires its own lifespan into the Starlette app it returns, but
        # mounting it (below) makes that dead code: the host app's lifespan must enter the
        # session manager itself (docs/run/asgi.md).
        async with mcp_tools.session_manager.run():
            yield

    app = FastAPI(title="AgentProbe Demo Agents", lifespan=lifespan)

    @app.middleware("http")
    async def label(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-AgentProbe-Demo"] = WARNING
        return response

    app.include_router(routes_support.build_router("v1"))
    app.include_router(routes_support.build_router("v2"))
    app.include_router(routes_rag.router)
    app.include_router(routes_vulnerable.router)
    app.mount(MCP_ROUTE, mcp_tools.streamable_http_app())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def about() -> dict[str, str]:
        return {"service": "AgentProbe demo agents", "warning": WARNING}

    return app


app = create_app()


@contextmanager
def serve_in_background(host: str = "127.0.0.1") -> Iterator[str]:
    """Serves every demo agent on a free port from a daemon thread, for tests: yields the
    base URL (e.g. `http://127.0.0.1:53124`) and stops the server afterwards.

    Builds its own app rather than reusing the module-level `app` singleton: the MCP
    server's `session_manager` can only be `run()` once, and several test modules each call
    this once (module-scoped fixtures), so sharing one app across them would fail every
    server after the first.
    """
    server = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the demo agents did not start")
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=15)
