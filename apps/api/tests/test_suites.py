import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.models import TestCase
from apitest import SignUp

pytestmark = pytest.mark.integration

VALID_YAML = """
suite: demo-suite
agent: demo-bot
runs_per_case: 2
cases:
  - id: c1
    input: "hello"
    expect:
      - judge: contains
        value: "hi"
"""

VALID_YAML_V2 = """
suite: demo-suite
agent: demo-bot
runs_per_case: 3
cases:
  - id: c1
    input: "hello"
    expect:
      - judge: contains
        value: "hi"
  - id: c2
    input: "bye"
    expect:
      - judge: contains
        value: "bye"
"""

INVALID_YAML = "suite: demo\nagent: [unterminated\n"


async def new_project(client: httpx.AsyncClient, name: str = "demo") -> dict[str, str]:
    r = await client.post("/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_create_suite_syncs_test_cases(sign_up: SignUp, db: AsyncSession) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    r = await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    assert r.status_code == 201, r.text
    suite = r.json()
    assert suite["name"] == "demo-suite"
    assert suite["version"] == 1
    assert suite["case_count"] == 1
    rows = (await db.scalars(select(TestCase).where(TestCase.suite_id == suite["id"]))).all()
    assert [row.case_key for row in rows] == ["c1"]
    assert rows[0].expectations == {"judges": [{"judge": "contains", "value": "hi"}]}


async def test_create_suite_with_invalid_yaml_is_rejected(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    r = await alice.post(f"/projects/{project['id']}/suites", json={"yaml": INVALID_YAML})
    assert r.status_code == 422
    assert r.json()["error"]["details"]


async def test_list_suites(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    r = await alice.get(f"/projects/{project['id']}/suites")
    assert r.status_code == 200
    [suite] = r.json()
    assert suite["name"] == "demo-suite"
    assert suite["case_count"] == 1


async def test_put_same_yaml_does_not_bump_version(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = (
        await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    ).json()
    r = await alice.put(f"/suites/{created['id']}", json={"yaml": VALID_YAML})
    assert r.status_code == 200
    assert r.json()["version"] == 1


async def test_put_changed_yaml_bumps_version_and_keeps_old_rows(
    sign_up: SignUp, db: AsyncSession
) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = (
        await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    ).json()
    r = await alice.put(f"/suites/{created['id']}", json={"yaml": VALID_YAML_V2})
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["version"] == 2
    assert updated["case_count"] == 2
    v1_rows = (
        await db.scalars(
            select(TestCase).where(TestCase.suite_id == created["id"], TestCase.suite_version == 1)
        )
    ).all()
    assert [row.case_key for row in v1_rows] == ["c1"]  # untouched, still there


async def test_put_invalid_yaml_is_rejected(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = (
        await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    ).json()
    r = await alice.put(f"/suites/{created['id']}", json={"yaml": INVALID_YAML})
    assert r.status_code == 422


async def test_duplicate_suite_name_rejected(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    assert (
        await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    ).status_code == 201
    r = await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    assert r.status_code == 409


async def test_validate_endpoint_does_not_save(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.post("/suites/validate", json={"yaml": VALID_YAML})
    assert r.status_code == 200
    assert r.json() == {"valid": True, "case_count": 1, "issues": []}
    assert (await alice.get("/projects")).json() == []  # nothing persisted


async def test_validate_endpoint_reports_issues(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.post("/suites/validate", json={"yaml": INVALID_YAML})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert body["issues"]


async def test_get_nonexistent_suite_put_is_404(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.put("/suites/00000000-0000-0000-0000-000000000000", json={"yaml": VALID_YAML})
    assert r.status_code == 404
