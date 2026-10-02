import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.models import SuiteVersion, TestCase
from apitest import SignUp
from runtest import NullQueue

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


async def test_validate_endpoint_locates_syntax_errors(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.post("/suites/validate", json={"yaml": INVALID_YAML})
    assert r.status_code == 200
    [issue] = r.json()["issues"]
    # PyYAML marks an unterminated flow sequence where it gave up: the end of the stream.
    assert (issue["line"], issue["col"]) == (3, 1)
    assert "line 3, column 1" in issue["message"]
    assert issue["path"] is None


async def test_validate_endpoint_locates_schema_violations(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    bad = VALID_YAML + "extra_field: true\n"
    r = await alice.post("/suites/validate", json={"yaml": bad})
    assert r.status_code == 200
    [issue] = r.json()["issues"]
    assert issue["path"] == "extra_field"
    # The offending key's value, on the line appended after VALID_YAML's own lines.
    assert (issue["line"], issue["col"]) == (
        len(VALID_YAML.splitlines()) + 1,
        len("extra_field: ") + 1,
    )


async def test_get_nonexistent_suite_put_is_404(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.put("/suites/00000000-0000-0000-0000-000000000000", json={"yaml": VALID_YAML})
    assert r.status_code == 404


async def test_get_suite_returns_yaml_source(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    created = (
        await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    ).json()
    r = await alice.get(f"/suites/{created['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["yaml"] == VALID_YAML
    assert body["version"] == 1
    assert body["case_count"] == 1


async def test_get_nonexistent_suite_is_404(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    r = await alice.get("/suites/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


REORDERED_YAML_V3 = """
suite: demo-suite
agent: demo-bot
runs_per_case: 2
cases:
  - id: z-first-in-yaml
    input: "first"
    attack: prompt_injection.direct
    context: ["doc one", "doc two"]
    expect:
      - judge: contains
        value: "x"
  - id: a-second-in-yaml
    input: "second"
    expect:
      - judge: not_contains
        values: ["y"]
"""


async def test_versions_keep_their_yaml_cases_and_run_counts(
    sign_up: SignUp, app: FastAPI, db: AsyncSession
) -> None:
    app.state.queue = NullQueue()  # runs are only counted here, never executed
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    agent = {"adapter_type": "http", "url": "https://agent.example.com/chat"}
    r = await alice.post(
        f"/projects/{project['id']}/agents", json={"name": "demo-bot", "config": agent}
    )
    assert r.status_code == 201, r.text
    suite = (
        await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    ).json()
    base = f"/suites/{suite['id']}"
    assert (await alice.post(f"{base}/runs", json={})).status_code == 202
    for yaml in (VALID_YAML_V2, REORDERED_YAML_V3):
        assert (await alice.put(base, json={"yaml": yaml})).status_code == 200

    versions = (await alice.get(f"{base}/versions")).json()
    assert [(v["version"], v["case_count"], v["run_count"], v["has_yaml"]) for v in versions] == [
        (3, 2, 0, True),
        (2, 2, 0, True),
        (1, 1, 1, True),
    ]
    assert all(v["created_at"] for v in versions)
    for number, yaml in ((1, VALID_YAML), (2, VALID_YAML_V2), (3, REORDERED_YAML_V3)):
        assert (await alice.get(f"{base}/versions/{number}")).json() == {
            "version": number,
            "yaml": yaml,
        }

    # The current version's cases, in the YAML's order (not the key order), with their judges.
    cases = (await alice.get(f"{base}/cases")).json()
    assert [c["id"] for c in cases] == ["z-first-in-yaml", "a-second-in-yaml"]
    assert cases[0] == {
        "id": "z-first-in-yaml",
        "input": "first",
        "call": None,
        "attack": "prompt_injection.direct",
        "context_count": 2,
        "judges": [{"judge": "contains", "value": "x"}],
    }
    old = (await alice.get(f"{base}/cases", params={"version": 1})).json()
    assert [c["id"] for c in old] == ["c1"]

    # A version saved before migration 0005 has its cases but no YAML: listed, cases in key order.
    await db.execute(
        delete(SuiteVersion).where(SuiteVersion.suite_id == suite["id"], SuiteVersion.version == 3)
    )
    v3 = (await alice.get(f"{base}/versions")).json()[0]
    assert (v3["version"], v3["has_yaml"], v3["created_at"]) == (3, False, None)
    assert (await alice.get(f"{base}/versions/3")).json() == {"version": 3, "yaml": None}
    assert [c["id"] for c in (await alice.get(f"{base}/cases")).json()] == [
        "a-second-in-yaml",
        "z-first-in-yaml",
    ]

    for missing in (0, 4):
        assert (await alice.get(f"{base}/versions/{missing}")).status_code == 404
        assert (await alice.get(f"{base}/cases", params={"version": missing})).status_code == 404


async def test_an_unchanged_put_adds_no_version(sign_up: SignUp) -> None:
    alice = await sign_up("alice@example.com")
    project = await new_project(alice)
    suite = (
        await alice.post(f"/projects/{project['id']}/suites", json={"yaml": VALID_YAML})
    ).json()
    await alice.put(f"/suites/{suite['id']}", json={"yaml": VALID_YAML})
    assert [v["version"] for v in (await alice.get(f"/suites/{suite['id']}/versions")).json()] == [
        1
    ]
