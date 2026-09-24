"""One FastAPI app, one process, one port: serves every bundled demo agent under a path
prefix. See README.md for the route list and the deliberately-vulnerable warning.
"""

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
