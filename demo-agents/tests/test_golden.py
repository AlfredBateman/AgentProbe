"""Golden tests: AgentProbe testing itself (PLAN.md B1.8).

Every planted flaw in vulnerabilities.json is detected by a real run of its suite against the
real demo agents (mock mode, core's `run_suite` over loopback HTTP); the same attack cases
pass on the well-behaved /support/v1, so AgentProbe isn't just flagging everything; and the
regression verdict tells a real regression (v1 -> v2) from flaky noise (v1 -> v1).
The definition of "detected" lives in `agentprobe_demo_agents.detection`, shared with
scripts/measure_detection.py so the published numbers and these tests can't drift apart.
"""

from collections.abc import Iterator

import pytest

from agentprobe_core.runner import RunSummary
from agentprobe_core.stats import compare_runs
from agentprobe_demo_agents import flaky
from agentprobe_demo_agents.detection import (
    FlawResult,
    RunKey,
    evaluate,
    load_manifest,
    required_runs,
    run_one,
)
from agentprobe_demo_agents.main import serve_in_background

FLAWS = load_manifest()
SMOKE = "suites/examples/smoke.yaml"
V1 = (SMOKE, "/support/v1")
V2 = (SMOKE, "/support/v2")


def labels(run: RunSummary) -> dict[str, str]:
    return {case.case_id: case.label for case in run.cases}


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    with serve_in_background() as url:
        yield url


@pytest.fixture(scope="module")
async def runs(base_url: str) -> dict[RunKey, RunSummary]:
    flaky.reset()
    return {key: await run_one(base_url, key) for key in required_runs(FLAWS)}


@pytest.fixture(scope="module")
def results(runs: dict[RunKey, RunSummary]) -> dict[str, FlawResult]:
    return {result.flaw.id: result for result in evaluate(FLAWS, runs)}


@pytest.mark.parametrize("flaw_id", [flaw.id for flaw in FLAWS])
def test_the_planted_flaw_is_detected(results: dict[str, FlawResult], flaw_id: str) -> None:
    result = results[flaw_id]
    assert result.detected, result.reason
    assert result.as_expected, f"expected {result.flaw.expected}, got {result.labels}"


@pytest.mark.parametrize("flaw_id", [flaw.id for flaw in FLAWS])
def test_its_negative_control_passes(results: dict[str, FlawResult], flaw_id: str) -> None:
    result = results[flaw_id]
    assert result.control_passed, result.control_reason


def test_every_planted_flaw_is_detected(results: dict[str, FlawResult]) -> None:
    detected = [flaw_id for flaw_id, result in results.items() if result.detected]
    print(f"{len(detected)} of {len(FLAWS)} planted flaws detected")
    assert len(detected) == len(FLAWS) == 7


def test_every_attack_case_passes_on_the_well_behaved_agent(
    runs: dict[RunKey, RunSummary],
) -> None:
    attack_cases = {case_id for flaw in FLAWS if flaw.suite == SMOKE for case_id in flaw.case_ids}
    v1 = labels(runs[V1])
    assert attack_cases <= v1.keys()
    assert {case_id: v1[case_id] for case_id in attack_cases} == dict.fromkeys(
        attack_cases, "stable-pass"
    )


def test_v1_to_v2_is_a_regression_on_the_refund_case(runs: dict[RunKey, RunSummary]) -> None:
    report = compare_runs(runs[V1].case_summaries(), runs[V2].case_summaries(), runs[V1].statistics)
    assert report.verdict == "regression"
    assert report.regressed == ["refund-outside-window"]


async def test_v1_to_v1_is_no_change_and_the_seeded_flakiness_is_labelled_flaky(
    base_url: str,
) -> None:
    flaky.reset()
    first = await run_one(base_url, V1)
    second = await run_one(base_url, V1)  # the next seeded draws: a different outcome
    assert labels(first)["order-status"] == "flaky"
    assert {c.case_id for c in first.cases if c.label != "stable-pass"} == {"order-status"}
    order_status = [
        next(c.summary.passes for c in run.cases if c.case_id == "order-status")
        for run in (first, second)
    ]
    assert order_status[0] != order_status[1], "the two runs should see different noise"

    report = compare_runs(first.case_summaries(), second.case_summaries(), first.statistics)
    assert report.verdict == "no_change"
    assert report.regressed == []
