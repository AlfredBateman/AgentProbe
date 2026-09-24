"""End to end: drive every credential through the API with verbose logging on, and prove
none of them reaches the log output.
"""

import io
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI

from agentprobe_api.logs import configure_logging
from apitest import PASSWORD, ClientFactory, SignUp

pytestmark = pytest.mark.integration


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    # Requested before `app`/`db` so SQLAlchemy sees INFO when the connection opens: the
    # worst case, where every statement and its bound parameters are logged.
    stream = io.StringIO()
    handler = configure_logging("DEBUG", stream)
    sql = logging.getLogger("sqlalchemy.engine")
    previous = sql.level
    sql.setLevel(logging.INFO)
    yield stream
    sql.setLevel(previous)
    logging.getLogger().removeHandler(handler)


async def test_secrets_never_reach_logs(
    log_output: io.StringIO, app: FastAPI, sign_up: SignUp, clients: ClientFactory
) -> None:
    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError(f"exploded with {key}")

    alice = await sign_up("alice@example.com")
    secrets = [PASSWORD, alice.cookies["access_token"], alice.cookies["refresh_token"]]
    await alice.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    await alice.post(
        "/auth/login", json={"email": "alice@example.com", "password": "wrong " + PASSWORD}
    )
    await alice.post("/auth/refresh")
    secrets += [alice.cookies["access_token"], alice.cookies["refresh_token"]]

    project = (await alice.post("/projects", json={"name": "p"})).json()
    key = (await alice.post(f"/projects/{project['id']}/api-keys", json={"label": "ci"})).json()[
        "key"
    ]
    secrets.append(key)
    keyed = clients(headers={"Authorization": f"Bearer {key}"})
    await keyed.get("/projects")
    await keyed.get(f"/projects?token={secrets[1]}&api_key={key}")  # stream-token style query
    await keyed.get("/boom")  # unhandled error: traceback is logged
    await clients(headers={"Authorization": f"Bearer {key}x"}).get("/projects")  # bad key

    text = log_output.getvalue()
    assert '"logger": "agentprobe.access"' in text and "sqlalchemy.engine" in text  # captured
    assert "Traceback" in text
    for secret in secrets:
        assert secret not in text, f"secret {secret[:6]}… leaked into logs"
