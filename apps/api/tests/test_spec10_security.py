"""Security considerations, one named test per item not covered elsewhere, plus the
API's security headers, CORS and CSRF guarantees.
"""

import re
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.db import get_db
from agentprobe_api.main import MAX_BODY_BYTES, SECURITY_HEADERS, create_app
from agentprobe_api.models import Suite
from agentprobe_api.security import encode_token
from agentprobe_api.settings import Settings
from agentprobe_core.llm.types import ROLES
from agentprobe_core.suite.parser import MAX_FILE_BYTES
from apitest import PASSWORD, WEB_ORIGIN, SignUp, make_settings
from runtest import SMALL_YAML, make_project, wait_for_run

ROOT = Path(__file__).parents[3]
EVIL = "https://evil.example"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


async def _no_db() -> AsyncIterator[None]:
    yield None  # nothing here may reach the database: every check runs before it


@pytest.fixture
def offline_app() -> FastAPI:
    app = create_app(make_settings())
    app.dependency_overrides[get_db] = _no_db
    return app


def client(app: FastAPI, **headers: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.test", headers=headers
    )


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


# --- CSRF: every cookie-authenticated mutation needs the web Origin ----------------------


def mutating_routes(app: FastAPI) -> list[tuple[str, str]]:
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() in MUTATING
    )


@pytest.mark.parametrize("origin", [EVIL, None, "null", WEB_ORIGIN + ".evil.example"])
async def test_csrf_every_mutating_route_rejects_a_foreign_or_missing_origin(
    offline_app: FastAPI, origin: str | None
) -> None:
    """A browser carrying a valid session cookie is refused on every mutating route, the auth
    routes included, unless the request comes from WEB_ORIGIN (ADR 0009). Enumerated from the
    app itself, so a new route is covered the moment it exists.
    """
    settings: Settings = offline_app.state.settings
    assert settings.jwt_secret is not None
    session = encode_token(settings.jwt_secret, "access", uuid.uuid4(), timedelta(minutes=5))
    headers = {"Origin": origin} if origin is not None else {}
    routes = mutating_routes(offline_app)
    assert len(routes) >= 20  # the enumeration found the app's routes
    async with client(offline_app, **headers) as c:
        c.cookies.set("access_token", session)
        c.cookies.set("refresh_token", "r" * 43)
        for method, path in routes:
            # A body that validates for register/login, which check the Origin in the handler.
            r = await c.request(
                method, concrete(path), json={"email": "alice@example.com", "password": PASSWORD}
            )
            assert r.status_code == 403, (method, path, r.status_code, r.text)
            assert r.json()["error"]["message"] == "Cross-origin request rejected", (method, path)


# --- CORS: locked to the web origin, and only where a browser needs it --------------------


@pytest.mark.parametrize("origin", [EVIL, WEB_ORIGIN])
async def test_cors_no_route_grants_cross_origin_reads(offline_app: FastAPI, origin: str) -> None:
    """There is no CORS middleware: the browser reaches the API through the web app's own
    /api proxy (same origin). The one exception is a token-authenticated SSE stream, which
    allows WEB_ORIGIN only (test_runs.py::test_stream_token_fallback). A preflight is refused,
    so no cross-origin script can send a credentialed write.
    """
    async with client(offline_app, Origin=origin) as c:
        for r in (
            await c.get("/health"),
            await c.get(f"/runs/{uuid.uuid4()}"),
            await c.options(
                "/projects",
                headers={
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            ),
        ):
            assert "access-control-allow-origin" not in r.headers
            assert "access-control-allow-credentials" not in r.headers
        assert r.status_code == 405  # the preflight


# --- Security headers ----------------------------------------------------------------------


async def test_security_headers_are_on_every_response(offline_app: FastAPI) -> None:
    @offline_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    @offline_app.get("/html")
    def html() -> HTMLResponse:  # like the HTML export, which sets a stricter CSP of its own
        return HTMLResponse("<p>x</p>", headers={"Content-Security-Policy": "default-src 'none'"})

    expected = {k.decode(): v.decode() for k, v in SECURITY_HEADERS.items()}
    async with client(offline_app) as c:
        for path, status in (("/health", 200), ("/nope", 404), ("/boom", 500)):
            r = await c.get(path)
            assert r.status_code == status
            for name, value in expected.items():
                assert r.headers.get(name) == value, (path, name)
            assert r.headers["x-request-id"]
        own = await c.get("/html")
        assert own.headers.get_list("content-security-policy") == ["default-src 'none'"]
        assert own.headers["x-frame-options"] == "DENY"
        docs = await c.get("/docs")  # Swagger UI loads its script from a CDN
        assert docs.status_code == 200
        assert "content-security-policy" not in docs.headers
        assert docs.headers["x-content-type-options"] == "nosniff"


# --- Size limits ---------------------------------------------------------------------------


async def test_request_bodies_over_the_cap_are_refused_before_reading(
    offline_app: FastAPI,
) -> None:
    """Every body is read into memory before validation, the anonymous /auth/register's too,
    so the cap guards the instance's memory. A declared length over it is refused unread; a
    chunked body is cut off as soon as it passes the cap.
    """
    chunk = b"x" * (1024 * 1024)

    async def chunked() -> AsyncIterator[bytes]:
        for _ in range(MAX_BODY_BYTES // len(chunk) + 2):
            yield chunk

    async with client(offline_app, Origin=WEB_ORIGIN) as c:
        declared = await c.post(
            "/auth/register",
            content=b"{}",
            headers={"Content-Length": str(MAX_BODY_BYTES + 1), "Content-Type": "application/json"},
        )
        streamed = await c.post(
            "/auth/register", content=chunked(), headers={"Content-Type": "application/json"}
        )
        for r in (declared, streamed):
            assert r.status_code == 413, r.text
            assert r.json()["error"]["code"] == "payload_too_large"
            assert r.headers["x-content-type-options"] == "nosniff"
        under = await c.post("/auth/register", json={"email": "x"})  # reaches validation
        assert under.status_code == 422


@pytest.mark.integration
async def test_spec10_oversized_suite_yaml_is_rejected_and_nothing_saved(
    sign_up: SignUp, db: AsyncSession
) -> None:
    alice = await sign_up("alice@example.com")
    project = (await alice.post("/projects", json={"name": "p"})).json()
    huge = SMALL_YAML + "# " + "x" * MAX_FILE_BYTES + "\n"
    r = await alice.post(f"/projects/{project['id']}/suites", json={"yaml": huge})
    assert r.status_code == 422
    assert "over the" in r.json()["error"]["details"][0]["message"]
    checked = await alice.post("/suites/validate", json={"yaml": huge})
    assert checked.status_code == 200 and checked.json()["valid"] is False
    saved = select(func.count()).select_from(Suite).where(Suite.project_id == project["id"])
    assert await db.scalar(saved) == 0


# --- Attacks run only against registered agents ------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("demo_env")
async def test_spec10_runs_target_only_the_suites_own_registered_agent(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    """A run's target is the agent the suite names, registered in the suite's own project.
    A request can't supply a target, and an agent registered in another project (even the
    caller's own, even with the same name) is never used.
    """
    alice = await sign_up("alice@example.com")
    bob = await sign_up("bob@example.com")
    url = f"{demo_url}/support/v1/chat"
    home = await make_project(alice, url)
    await make_project(bob, url)  # bob's own "support-v1"

    elsewhere = (await alice.post("/projects", json={"name": "no-agent"})).json()
    suite = await alice.post(f"/projects/{elsewhere['id']}/suites", json={"yaml": SMALL_YAML})
    refused = await alice.post(f"/suites/{suite.json()['id']}/runs", json={})
    assert refused.status_code == 422
    assert "isn't in this project" in refused.json()["error"]["message"]

    for injected in ({"url": "http://169.254.169.254/"}, {"agent_id": home["agent_id"]}):
        r = await alice.post(f"/suites/{home['suite_id']}/runs", json=injected)
        assert r.status_code == 422, injected

    started = await alice.post(f"/suites/{home['suite_id']}/runs", json={})
    assert started.status_code == 202
    assert started.json()["agent_id"] == home["agent_id"]
    listed = [
        [run["id"] for run in (await alice.get(f"/projects/{p}/runs")).json()]
        for p in (home["project_id"], elsewhere["id"])
    ]
    assert listed == [[started.json()["id"]], []]
    await wait_for_run(alice, app, started.json()["id"])  # nothing left running at teardown


# --- .env.example documents every setting ------------------------------------------------

# Read by the code but set by the platform or the build, never by an operator's .env.
PLATFORM_SET = {
    "RENDER_GIT_COMMIT",
    "RENDER_EXTERNAL_HOSTNAME",
    "NODE_ENV",
    "NEXT_OUTPUT",  # apps/web/Dockerfile
    "GITHUB_EVENT_PATH",  # the GitHub Action's runner
    "GITHUB_REPOSITORY",
}
# Documented in .env.example but read by a library or tool, not by our code.
READ_ELSEWHERE = {
    "GEMINI_API_KEY": "LiteLLM",
    "FORWARDED_ALLOW_IPS": "uvicorn",
}
ENV_READ = re.compile(
    r"""(?:environ(?:\.get)?\s*[\[(]|getenv\(|\benv(?:\.get)?\s*[\[(]|_(?:int|float)\(env,\s*"""
    r"""|_ENV\s*=\s*)\s*["']([A-Z][A-Z0-9_]+)["']"""
)


def env_vars_read_by_code() -> set[str]:
    names = {name.upper() for name in Settings.model_fields}
    names |= {f"LLM_MODEL_{role.upper()}" for role in ROLES}  # read as an f-string per role
    sources = [
        *ROOT.glob("packages/*/src/**/*.py"),
        *ROOT.glob("apps/api/src/**/*.py"),
        *ROOT.glob("demo-agents/src/**/*.py"),
        *ROOT.glob("action/*.py"),
        ROOT / "conftest.py",  # the DB-test guard
    ]
    for path in sources:
        names |= set(ENV_READ.findall(path.read_text("utf-8")))
    for path in [*ROOT.glob("apps/web/src/**/*.ts"), *ROOT.glob("apps/web/src/**/*.tsx")]:
        if ".test." not in path.name:
            names |= set(re.findall(r"process\.env\.([A-Z][A-Z0-9_]+)", path.read_text("utf-8")))
    return names


def env_example_names() -> set[str]:
    text = (ROOT / ".env.example").read_text("utf-8")
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, flags=re.MULTILINE))


def test_spec10_env_example_documents_every_variable_the_code_reads() -> None:
    read = env_vars_read_by_code()
    assert {"DATABASE_URL", "JWT_SECRET", "LLM_RPM", "AGENT_MODE", "PROXY_SECRET"} <= read
    missing = read - PLATFORM_SET - env_example_names()
    assert not missing, f"read by the code but not in .env.example: {sorted(missing)}"


def test_spec10_env_example_lists_nothing_the_code_ignores() -> None:
    stale = env_example_names() - env_vars_read_by_code() - READ_ELSEWHERE.keys()
    assert not stale, f"in .env.example but read by nothing: {sorted(stale)}"


def test_spec10_env_example_holds_no_real_secret() -> None:
    """The public repo's template: every secret is empty or an obvious placeholder."""
    for line in (ROOT / ".env.example").read_text("utf-8").splitlines():
        name, sep, value = line.partition("=")
        if not sep or line.startswith("#"):
            continue
        if re.search(r"(SECRET|_KEY|_TOKEN|PASSWORD)$", name):
            assert value in ("", "change-me"), name
        if "://" in value and "@" in value:  # a URL with credentials
            assert "user:password@" in value and "example" in value, name
