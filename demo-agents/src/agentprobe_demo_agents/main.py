"""One FastAPI app, one process, one port: serves every bundled demo agent under a path
prefix. See README.md for the route list and the deliberately-vulnerable warning.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn
from fastapi import FastAPI

from agentprobe_demo_agents import routes_rag, routes_support, routes_vulnerable


def create_app() -> FastAPI:
    app = FastAPI(title="AgentProbe Demo Agents")
    app.include_router(routes_support.build_router("v1"))
    app.include_router(routes_support.build_router("v2"))
    app.include_router(routes_rag.router)
    app.include_router(routes_vulnerable.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


@contextmanager
def serve_in_background(host: str = "127.0.0.1") -> Iterator[str]:
    """Serves every demo agent on a free port from a daemon thread, for tests: yields the
    base URL (e.g. `http://127.0.0.1:53124`) and stops the server afterwards.
    """
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=0, log_level="warning"))
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
