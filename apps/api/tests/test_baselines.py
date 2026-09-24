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

    missing = await alice.get(f"/projects/{ids['project_id']}/baselines/main")
    assert missing.status_code == 404

    set_r = await alice.post(
        f"/projects/{ids['project_id']}/baseline", json={"branch": "main", "run_id": done["id"]}
    )
    assert set_r.status_code == 201, set_r.text
    body = set_r.json()
    assert (body["branch"], body["run_id"], body["suite_id"]) == (
        "main",
        done["id"],
        ids["suite_id"],
    )

    get_r = await alice.get(f"/projects/{ids['project_id']}/baselines/main")
    assert get_r.status_code == 200
    assert get_r.json()["run_id"] == done["id"]

    # Re-setting the same branch (a later "good" run) replaces it rather than erroring.
    run2 = await start_run(alice, ids["suite_id"])
    done2 = await wait_for_run(alice, app, run2["id"])
    replace_r = await alice.post(
        f"/projects/{ids['project_id']}/baseline", json={"branch": "main", "run_id": done2["id"]}
    )
    assert replace_r.status_code == 201
    assert (await alice.get(f"/projects/{ids['project_id']}/baselines/main")).json()[
        "run_id"
    ] == done2["id"]


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
