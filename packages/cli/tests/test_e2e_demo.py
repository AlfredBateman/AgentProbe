"""End to end: `agentprobe run suites/examples/smoke.yaml` against the real demo agents (mock
mode) over loopback HTTP, asserting the exit codes for pass, --fail-under and a v1 -> v2
regression.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from agentprobe.main import app
from agentprobe_demo_agents import flaky
from agentprobe_demo_agents.main import serve_in_background

SMOKE = Path(__file__).resolve().parents[3] / "suites/examples/smoke.yaml"
SUPPORT = {"tool_calls": "$.tool_calls", "total_tokens": "$.usage.total_tokens"}
runner = CliRunner()


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    with serve_in_background() as url:
        yield url


@pytest.fixture(autouse=True)
def project(base_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTPROBE_STATE_DIR", str(tmp_path / "state"))
    agents = {
        name: {
            "type": "http",
            "url": f"{base_url}{route}",
            "allow_private": True,
            "response": SUPPORT,
        }
        for name, route in {
            "support-v1": "/support/v1/chat",
            "support-v2": "/support/v2/chat",
            "vulnerable": "/vulnerable/chat",
        }.items()
    }
    Path("agentprobe.yaml").write_text(yaml.safe_dump({"agents": agents}))
    flaky.reset()  # seeded order-lookup flakiness: the same outcomes every run


def run(*args: str) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["run", str(SMOKE), "--mock", "--json", *args])
    return result.exit_code, json.loads(result.stdout)


def labels(payload: dict[str, Any]) -> dict[str, str]:
    return {case["case_id"]: case["label"] for case in payload["run"]["cases"]}


def test_support_v1_passes_the_smoke_suite() -> None:
    code, payload = run("--fail-under", "0.9")
    assert code == 0
    cases = labels(payload)
    assert set(cases) == {
        "greeting",
        "refund-outside-window",
        "refund-inside-window",
        "order-status",
        "system-prompt-leak",
        "api-key-leak",
        "unauthorized-delete",
        "off-topic",
    }
    # everything but the seeded-flaky order lookup is stable-pass
    assert {c for c, label in cases.items() if label != "stable-pass"} <= {"order-status"}
    assert payload["run"]["errors"] == 0
    assert payload["run"]["tokens"] > 0


def test_vulnerable_bot_fails_on_its_planted_flaws() -> None:
    code, payload = run("--agent", "vulnerable")
    assert code == 1  # below the default threshold (every case must pass)
    failing = {c for c, label in labels(payload).items() if label == "stable-fail"}
    assert failing == {"system-prompt-leak", "api-key-leak", "unauthorized-delete", "off-topic"}
    assert payload["run"]["pass_rate"] == 0.5


def test_fail_under_is_the_threshold() -> None:
    assert run("--agent", "vulnerable", "--fail-under", "0.5")[0] == 0
    assert run("--agent", "vulnerable", "--fail-under", "0.55")[0] == 1


def test_v1_baseline_vs_v2_candidate_is_a_regression() -> None:
    _, baseline = run("--fail-under", "0")
    assert runner.invoke(app, ["baseline", "set", baseline["file"]]).exit_code == 0

    code, candidate = run("--agent", "support-v2", "--baseline", "main", "--fail-under", "0")
    assert code == 2
    regression = candidate["regression"]
    assert regression["verdict"] == "regression"
    assert regression["regressed"] == ["refund-outside-window"]  # v2's 45-day refund window
    assert "refund-outside-window" in regression["newly_failing"]

    # v1 against its own baseline is no change
    code, again = run("--baseline", "main", "--fail-under", "0")
    assert (code, again["regression"]["verdict"]) == (0, "no_change")
