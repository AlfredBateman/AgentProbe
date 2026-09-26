"""Golden test through the whole server path: the vulnerable demo bot's planted flaws are
detected by a run started over the API, executed on the inline backend and read back from
the results endpoint (Neon test database). The core-only golden tests are
demo-agents/tests/test_golden.py; this proves the server reports the same thing.
"""

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.main import create_app
from agentprobe_demo_agents.detection import load_manifest
from apitest import SignUp, bind_db, make_settings
from runtest import SMOKE_YAML, make_project, start_run, wait_for_run

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("demo_env")]


@pytest.fixture
def app(db: AsyncSession) -> FastAPI:
    return bind_db(create_app(make_settings()), db)


async def test_the_vulnerable_bots_planted_flaws_are_detected_through_the_api(
    sign_up: SignUp, app: FastAPI, demo_url: str
) -> None:
    flaws = [flaw for flaw in load_manifest() if flaw.route == "/vulnerable"]
    assert len(flaws) == 5
    alice = await sign_up("alice@example.com")
    ids = await make_project(alice, f"{demo_url}/vulnerable/chat", yaml=SMOKE_YAML)
    run = await start_run(alice, ids["suite_id"])
    done = await wait_for_run(alice, app, run["id"])
    assert (done["status"], done["error"]) == ("completed", None)

    rows = (await alice.get(f"/runs/{run['id']}/results")).json()
    labels = {row["case"]: row["label"] for row in rows}
    for flaw in flaws:
        for case_id in flaw.case_ids:
            assert labels[case_id] == flaw.expected, flaw.id
    # Only the planted flaws are flagged: the rest of the suite passes on this agent.
    flagged = {case_id for case_id, label in labels.items() if label != "stable-pass"}
    assert flagged == {case_id for flaw in flaws for case_id in flaw.case_ids}
