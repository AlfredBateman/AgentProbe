"""Error format and request-context middleware. Offline: get_db is stubbed."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from agentprobe_api.db import get_db
from agentprobe_api.main import create_app
from apitest import client_for, make_settings


@pytest.fixture
def app() -> FastAPI:
    app = create_app(make_settings())

    async def no_db() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_db] = no_db

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("password=hunter2 exploded")

    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(app) as c:
        yield c


def assert_error_shape(r: httpx.Response, status: int, code: str) -> None:
    assert r.status_code == status
    body = r.json()["error"]
    assert body["code"] == code
    assert isinstance(body["message"], str)
    assert body["request_id"] == r.headers["x-request-id"]


async def test_unknown_route_uses_error_format(client: httpx.AsyncClient) -> None:
    assert_error_shape(await client.get("/nope"), 404, "not_found")


async def test_method_not_allowed_uses_error_format(client: httpx.AsyncClient) -> None:
    assert_error_shape(await client.delete("/health"), 405, "method_not_allowed")


async def test_validation_error_never_echoes_input(client: httpx.AsyncClient) -> None:
    r = await client.post("/auth/register", json={"email": "not-an-email", "password": "pw-9x7q"})
    assert_error_shape(r, 422, "validation_error")
    assert "pw-9x7q" not in r.text
    assert {tuple(d["loc"]) for d in r.json()["error"]["details"]} == {
        ("body", "email"),
        ("body", "password"),
    }


async def test_form_encoded_body_is_rejected(client: httpx.AsyncClient) -> None:
    # A cross-site HTML form can only send form/text bodies; JSON endpoints refuse them.
    r = await client.post("/auth/login", data={"email": "a@example.com", "password": "x" * 12})
    assert_error_shape(r, 422, "validation_error")


async def test_unhandled_error_is_generic_500_with_request_id(client: httpx.AsyncClient) -> None:
    r = await client.get("/boom")
    assert_error_shape(r, 500, "internal_error")
    assert "hunter2" not in r.text


async def test_request_id_is_propagated_when_safe(client: httpx.AsyncClient) -> None:
    r = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


async def test_unsafe_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    r = await client.get("/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert r.headers["x-request-id"] != "bad id\nwith newline"
    assert len(r.headers["x-request-id"]) == 32


async def test_missing_credentials_is_401(client: httpx.AsyncClient) -> None:
    r = await client.get("/projects")
    assert_error_shape(r, 401, "unauthenticated")
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer eyJhbGciOi.x.y", "Bearer"])
async def test_non_api_key_authorization_is_401(client: httpx.AsyncClient, header: str) -> None:
    assert_error_shape(
        await client.get("/projects", headers={"Authorization": header}), 401, "unauthenticated"
    )
