"""POST /projects/{id}/baseline, GET /projects/{id}/baselines/{branch} (ADR 0018)."""

import uuid

import pytest
from fastapi import FastAPI

from apitest import SignUp
from runtest import SMOKE_YAML, make_project, start_run, wait_for_run

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]


async def test_set_and_get_baseline(sign_up: SignUp, app: FastAPI, demo_url: str) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])

    url = f"/projects/{ids['project_id']}/baselines/main"
    key = {"suite": "smoke", "agent": "support-v1"}
    missing = await alice.get(url, params=key)
    assert missing.status_code == 404

    set_r = await alice.post(
        f"/projects/{ids['project_id']}/baseline", json={"branch": "main", "run_id": done["id"]}
    )
    assert set_r.status_code == 201, set_r.text
    body = set_r.json()
    assert (body["branch"], body["run_id"], body["suite_id"], body["agent_id"]) == (
        "main",
        done["id"],
        ids["suite_id"],
        ids["agent_id"],
    )

    get_r = await alice.get(url, params=key)
    assert get_r.status_code == 200
    assert get_r.json()["run_id"] == done["id"]
    # The key is the suite and agent too, not just the branch.
    other = [{"suite": "nope", "agent": "support-v1"}, {"suite": "smoke", "agent_name": "x"}]
    for params in other:
        assert (await alice.get(url, params=params)).status_code == 404, params
    both = await alice.get(url, params={**key, "agent_name": "x"})
    assert both.status_code == 422

    # Re-setting the same branch (a later "good" run) replaces it rather than erroring.
    run2 = await start_run(alice, ids["suite_id"])
    done2 = await wait_for_run(alice, app, run2["id"])
    replace_r = await alice.post(
        f"/projects/{ids['project_id']}/baseline", json={"branch": "main", "run_id": done2["id"]}
    )
    assert replace_r.status_code == 201
    assert (await alice.get(url, params=key)).json()["run_id"] == done2["id"]


async def test_each_suite_keeps_its_own_baseline_on_a_branch(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    # Under the old (project, branch) key, the second suite's baseline replaced the first.
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    other = await alice.post(
        f"/projects/{ids['project_id']}/suites",
        json={"yaml": SMOKE_YAML.replace("suite: smoke", "suite: smoke-2")},
    )
    assert other.status_code == 201, other.text
    runs = {}
    for name, suite_id in (("smoke", ids["suite_id"]), ("smoke-2", other.json()["id"])):
        runs[name] = await wait_for_run(alice, app, (await start_run(alice, suite_id))["id"])
        r = await alice.post(
            f"/projects/{ids['project_id']}/baseline",
            json={"branch": "main", "run_id": runs[name]["id"]},
        )
        assert r.status_code == 201, r.text
    for name, run in runs.items():
        got = await alice.get(
            f"/projects/{ids['project_id']}/baselines/main",
            params={"suite": name, "agent": "support-v1"},
        )
        assert got.json()["run_id"] == run["id"], name


async def test_baseline_run_must_belong_to_the_project(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids_a = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    ids_b = await make_project(alice, f"{demo_url}/support/v1/chat", yaml=SMOKE_YAML)
    run = await wait_for_run(alice, app, (await start_run(alice, ids_a["suite_id"]))["id"])

    cross = await alice.post(
        f"/projects/{ids_b['project_id']}/baseline",
        json={"branch": "main", "run_id": run["id"]},
    )
    assert cross.status_code == 422

    unknown_run = await alice.post(
        f"/projects/{ids_a['project_id']}/baseline",
        json={"branch": "main", "run_id": str(uuid.uuid4())},
    )
    assert unknown_run.status_code == 404


async def test_baseline_requires_a_completed_run(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, "http://127.0.0.1:9/chat", max_retries=0)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    assert done["status"] == "failed"
    r = await alice.post(
        f"/projects/{ids['project_id']}/baseline", json={"branch": "main", "run_id": run["id"]}
    )
    assert r.status_code == 422
