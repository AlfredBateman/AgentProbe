import dataclasses
import json
import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agentprobe_core.stats import CaseSummary, compare_runs
from agentprobe_core.suite.schema import StatisticsConfig

PASS = CaseSummary(5, 5)
FAIL = CaseSummary(0, 5)


def run(*rates: tuple[int, int], prefix: str = "c") -> dict[str, CaseSummary]:
    return {f"{prefix}{i}": CaseSummary(p, n) for i, (p, n) in enumerate(rates)}


def test_identical_runs_are_no_change() -> None:
    runs = run((5, 5), (3, 5), (0, 5), (4, 5))
    report = compare_runs(runs, runs)
    assert report.verdict == "no_change"
    assert report.suite is not None
    assert report.suite.pass_rate_delta == 0
    assert (report.suite.p_worse, report.suite.p_better) == (1.0, 1.0)
    assert report.regressed == report.improved == []
    assert report.newly_failing == report.newly_flaky == report.no_longer_flaky == []


def test_single_case_hard_break_is_a_regression() -> None:
    report = compare_runs({"a": PASS}, {"a": FAIL})
    assert report.verdict == "regression"
    assert report.regressed == ["a"]
    assert report.cases[0].p_worse == pytest.approx(1 / 252)
    assert report.cases[0].pass_rate_delta == -1.0
    # One changed case is never significant at suite level (sign-flip p = 1/2).
    assert report.suite is not None
    assert not report.suite.regressed
    assert report.newly_failing == ["a"]


def test_p_value_exactly_at_alpha_is_significant() -> None:
    # 3/3 -> 0/3: p = 1/20 exactly, and 0.05 must mean 1/20, not the float just above it.
    report = compare_runs({"a": CaseSummary(3, 3)}, {"a": CaseSummary(0, 3)})
    assert report.cases[0].p_worse == 0.05
    assert report.cases[0].p_worse_threshold == 0.05
    assert report.verdict == "regression"


def _demo_suite(flaky: bool) -> tuple[dict[str, CaseSummary], dict[str, CaseSummary]]:
    """The demo: support-bot v1 vs v2 on a 30-case suite at 5 runs per case, where v2's
    prompt widens the refund window (demo-agents' planted regression) and the refund case
    goes from 5/5 to 0/5. Everything else is unchanged; with `flaky`, four order-lookup
    cases wobble at the demo agents' FLAKY_RATE (0.2) in both runs.
    """
    baseline = {f"stable-{i}": CaseSummary(5, 5) for i in range(25)}
    candidate = dict(baseline)
    wobble = [((4, 3), (3, 4), (5, 4), (4, 5)), ((5, 4), (4, 4), (4, 5), (3, 4))]
    for i in range(4):
        before, after = (wobble[0][i], wobble[1][i]) if flaky else ((5, 5), (5, 5))
        baseline[f"order-lookup-{i}"] = CaseSummary(before[0], 5)
        candidate[f"order-lookup-{i}"] = CaseSummary(after[0], 5)
    baseline["refund-policy-basic"] = CaseSummary(5, 5)
    candidate["refund-policy-basic"] = CaseSummary(0, 5)
    return baseline, candidate


@pytest.mark.parametrize("flaky", [False, True])
def test_demo_one_refund_case_breaking_in_30_is_a_regression(flaky: bool) -> None:
    baseline, candidate = _demo_suite(flaky)
    assert len(baseline) == len(candidate) == 30
    report = compare_runs(baseline, candidate)
    assert report.verdict == "regression"
    assert report.regressed == ["refund-policy-basic"]
    refund = next(c for c in report.cases if c.case_id == "refund-policy-basic")
    assert refund.p_worse == pytest.approx(1 / 252)
    # Unchanged 5/5 cases (min p = 1) and wobbling ones (min p >= 21/252) can't reach
    # 0.05, so Tarone's family is just the refund case: its threshold is alpha itself.
    assert refund.p_worse_threshold == 0.05
    # The suite's mean drop is below min_drop and the suite test isn't significant:
    # the per-case flag alone makes this a regression.
    assert report.suite is not None
    assert -report.suite.pass_rate_delta < 0.05
    assert not report.suite.regressed


@pytest.mark.parametrize("cases", [5, 13, 30, 100, 500])
@pytest.mark.parametrize("attempts", [3, 5, 10])
def test_one_hard_break_is_flagged_at_any_suite_size(cases: int, attempts: int) -> None:
    # Holm could not do this beyond 12 cases at 5 runs (1/252 * 13 > 0.05), nor beyond 1
    # case at 3 runs (1/20); Tarone drops the unchanged cases, which can never be
    # significant, from the family.
    baseline = {f"c{i}": CaseSummary(attempts, attempts) for i in range(cases)}
    candidate = baseline | {"c0": CaseSummary(0, attempts)}
    report = compare_runs(baseline, candidate)
    assert report.regressed == ["c0"]
    assert report.verdict == "regression"


@pytest.mark.parametrize("attempts", [1, 2])
def test_too_few_attempts_can_never_flag_a_case(attempts: int) -> None:
    # 1/1 -> 0/1 has p = 1/2 and 2/2 -> 0/2 has p = 1/6: above alpha whatever the family.
    report = compare_runs({"a": CaseSummary(attempts, attempts)}, {"a": CaseSummary(0, attempts)})
    assert report.regressed == []


def test_a_case_that_only_turns_flaky_is_weak_evidence_at_five_runs() -> None:
    # 5/5 -> 3/5: p = comb(8, 3) / comb(10, 5) = 56/252, far above alpha. Documented limit.
    baseline = {f"c{i}": PASS for i in range(30)}
    report = compare_runs(baseline, baseline | {"c0": CaseSummary(3, 5)})
    assert report.cases[0].p_worse == pytest.approx(56 / 252)
    assert report.verdict == "no_change"


def test_per_case_flag_needs_its_own_drop_to_reach_min_drop() -> None:
    baseline, candidate = {"a": CaseSummary(10, 10)}, {"a": CaseSummary(2, 10)}  # drop 0.8
    assert compare_runs(baseline, candidate).regressed == ["a"]
    strict = compare_runs(baseline, candidate, StatisticsConfig(min_drop=0.9))
    threshold = strict.cases[0].p_worse_threshold
    assert threshold is not None and strict.cases[0].p_worse <= threshold  # significant...
    assert strict.regressed == []  # ...but a drop of 0.8 is under min_drop
    assert strict.verdict == "no_change"


def test_threshold_is_none_where_the_step_down_stopped() -> None:
    # Two broken cases and one wobble: both breaks are rejected in turn, then the wobble
    # (4/5 -> 3/5, p = 1/2) is compared and fails; nothing after it is reached.
    baseline = {"a": PASS, "b": PASS, "c": CaseSummary(4, 5), "d": CaseSummary(3, 5)}
    candidate = {"a": FAIL, "b": FAIL, "c": CaseSummary(3, 5), "d": CaseSummary(3, 5)}
    cases = {c.case_id: c for c in compare_runs(baseline, candidate).cases}
    assert cases["a"].regressed and cases["b"].regressed
    assert cases["c"].p_worse_threshold is not None and not cases["c"].regressed
    assert cases["d"].p_worse_threshold is None


def test_widespread_small_drops_are_caught_at_suite_level() -> None:
    # 12 of 30 cases slip from 5/5 to 4/5: no case is individually significant, but a mean
    # drop of 0.08 with every change negative is (p = 1/2^12).
    baseline = run(*[(5, 5)] * 30)
    candidate = run(*[(4, 5)] * 12 + [(5, 5)] * 18)
    report = compare_runs(baseline, candidate)
    assert report.verdict == "regression"
    assert report.regressed == []
    assert report.suite is not None
    assert report.suite.regressed
    assert report.suite.pass_rate_delta == pytest.approx(-0.08)
    assert report.suite.p_worse == pytest.approx(1 / 2**12)
    assert report.suite.exact
    assert len(report.newly_flaky) == 12


def test_significant_drop_below_min_drop_is_not_flagged() -> None:
    # 20 of 100 cases drop by 0.2: p = 1/2^20, but the mean drop is only 0.04.
    baseline = run(*[(5, 5)] * 100)
    candidate = run(*[(4, 5)] * 20 + [(5, 5)] * 80)
    report = compare_runs(baseline, candidate)
    assert report.suite is not None
    assert report.suite.p_worse < 1e-5
    assert report.verdict == "no_change"
    lower_bar = compare_runs(baseline, candidate, StatisticsConfig(min_drop=0.03))
    assert lower_bar.verdict == "regression"


def test_drop_exactly_min_drop_is_flagged() -> None:
    # 5 of 20 cases drop by 0.2: mean drop is exactly 0.05 (in floats, 0.2 * 5 / 20 isn't).
    baseline = run(*[(5, 5)] * 20)
    candidate = run(*[(4, 5)] * 5 + [(5, 5)] * 15)
    report = compare_runs(baseline, candidate)
    assert report.suite is not None
    assert report.suite.p_worse == pytest.approx(1 / 32)
    assert report.verdict == "regression"


def test_alpha_from_config() -> None:
    baseline, candidate = {"a": PASS}, {"a": CaseSummary(1, 5)}  # p = 1/42 = 0.024
    assert compare_runs(baseline, candidate).verdict == "regression"
    strict = compare_runs(baseline, candidate, StatisticsConfig(alpha=0.01))
    assert strict.verdict == "no_change"
    assert strict.alpha == 0.01


def test_improvement_mirrors_regression() -> None:
    report = compare_runs({"a": FAIL}, {"a": PASS})
    assert report.verdict == "improvement"
    assert report.improved == ["a"]
    assert report.newly_passing == ["a"]


def test_regression_wins_over_improvement() -> None:
    # One case breaks while five others are fixed.
    baseline = run((5, 5), *[(0, 5)] * 5)
    candidate = run((0, 5), *[(5, 5)] * 5)
    report = compare_runs(baseline, candidate)
    assert report.regressed == ["c0"]
    assert len(report.improved) == 5
    assert report.suite is not None
    assert report.suite.pass_rate_delta > 0
    assert report.verdict == "regression"


def test_only_shared_cases_are_compared() -> None:
    baseline = {"kept": PASS, "removed": PASS}
    candidate = {"kept": PASS, "added": FAIL}  # a new failing case isn't a regression
    report = compare_runs(baseline, candidate)
    assert report.added == ["added"]
    assert report.removed == ["removed"]
    assert [c.case_id for c in report.cases] == ["kept"]
    assert report.suite is not None
    assert report.suite.cases == 1
    assert report.verdict == "no_change"


def test_no_shared_cases() -> None:
    report = compare_runs({"a": PASS}, {"b": FAIL})
    assert report.suite is None
    assert report.cases == []
    assert report.verdict == "no_change"
    assert (report.added, report.removed) == (["b"], ["a"])


def test_empty_runs() -> None:
    report = compare_runs({}, {})
    assert report.suite is None
    assert report.verdict == "no_change"


def test_unequal_attempts_between_runs() -> None:
    report = compare_runs({"a": CaseSummary(10, 10)}, {"a": CaseSummary(0, 5)})
    assert report.cases[0].p_worse == pytest.approx(1 / 3003)  # 1 / comb(15, 5)
    assert report.verdict == "regression"


def test_label_transitions() -> None:
    baseline = {
        "pass_to_fail": PASS,
        "flaky_to_fail": CaseSummary(3, 5),
        "pass_to_flaky": PASS,
        "fail_to_flaky": FAIL,
        "flaky_to_pass": CaseSummary(2, 5),
        "fail_to_pass": FAIL,
        "flaky_to_flaky": CaseSummary(4, 5),
    }
    candidate = {
        "pass_to_fail": FAIL,
        "flaky_to_fail": FAIL,
        "pass_to_flaky": CaseSummary(4, 5),
        "fail_to_flaky": CaseSummary(1, 5),
        "flaky_to_pass": PASS,
        "fail_to_pass": PASS,
        "flaky_to_flaky": CaseSummary(1, 5),
    }
    report = compare_runs(baseline, candidate)
    assert report.newly_failing == ["pass_to_fail", "flaky_to_fail"]
    assert report.newly_flaky == ["pass_to_flaky", "fail_to_flaky"]
    assert report.newly_passing == ["flaky_to_pass", "fail_to_pass"]
    assert report.no_longer_flaky == ["flaky_to_fail", "flaky_to_pass"]


def test_score_latency_and_cost_deltas() -> None:
    baseline = {
        "a": CaseSummary(5, 5, mean_score=0.9, mean_latency_ms=100, cost_usd=0.05),
        "b": CaseSummary(5, 5, mean_score=0.5, mean_latency_ms=300, cost_usd=None),
        "c": CaseSummary(5, 5),
    }
    candidate = {
        "a": CaseSummary(5, 5, mean_score=0.7, mean_latency_ms=150, cost_usd=0.10),
        "b": CaseSummary(5, 10, mean_score=0.6, mean_latency_ms=200, cost_usd=0.20),
        "c": CaseSummary(5, 5),
    }
    report = compare_runs(baseline, candidate)
    a, b, c = report.cases
    assert a.score_delta == pytest.approx(-0.2)
    assert a.latency_delta_ms == 50
    assert a.cost_per_attempt_delta_usd == pytest.approx(0.01)  # 0.02 - 0.01 per attempt
    assert b.cost_per_attempt_delta_usd is None  # baseline didn't report cost
    assert c.score_delta is c.latency_delta_ms is c.cost_per_attempt_delta_usd is None
    suite = report.suite
    assert suite is not None
    assert suite.score is not None and suite.latency_ms is not None and suite.cost_usd is not None
    assert (suite.score.baseline, suite.score.candidate) == pytest.approx((0.7, 0.65))
    assert suite.latency_ms.delta == pytest.approx(-25)  # mean(100, 300) -> mean(150, 200)
    assert suite.cost_usd.delta == pytest.approx(0.01)  # only case a reports cost in both


def test_no_metric_reported_gives_none() -> None:
    report = compare_runs({"a": PASS}, {"a": PASS})
    assert report.suite is not None
    assert report.suite.score is report.suite.latency_ms is report.suite.cost_usd is None


def test_report_is_json_serializable() -> None:
    report = compare_runs(run((5, 5), (3, 5)), run((2, 5), (3, 5)))
    decoded = json.loads(json.dumps(dataclasses.asdict(report)))
    assert decoded["verdict"] == report.verdict
    assert decoded["cases"][0]["baseline"]["passes"] == 5


@st.composite
def run_pairs(draw: st.DrawFn) -> tuple[dict[str, CaseSummary], dict[str, CaseSummary]]:
    size = draw(st.integers(1, 15))
    attempts = draw(st.integers(1, 10))
    passes = st.integers(0, attempts)
    baseline = {f"c{i}": CaseSummary(draw(passes), attempts) for i in range(size)}
    candidate = {f"c{i}": CaseSummary(draw(passes), attempts) for i in range(size)}
    return baseline, candidate


@given(run_pairs())
def test_swapping_runs_swaps_regressions_and_improvements(
    runs: tuple[dict[str, CaseSummary], dict[str, CaseSummary]],
) -> None:
    baseline, candidate = runs
    forward = compare_runs(baseline, candidate)
    backward = compare_runs(candidate, baseline)
    assert forward.regressed == backward.improved
    assert forward.improved == backward.regressed
    assert forward.suite is not None and backward.suite is not None
    assert forward.suite.regressed == backward.suite.improved
    assert forward.suite.improved == backward.suite.regressed
    assert forward.newly_flaky == backward.no_longer_flaky
    assert set(forward.newly_failing).isdisjoint(backward.newly_failing)


@given(run_pairs())
def test_a_run_compared_with_itself_never_changes(
    runs: tuple[dict[str, CaseSummary], dict[str, CaseSummary]],
) -> None:
    baseline, _ = runs
    assert compare_runs(baseline, baseline).verdict == "no_change"


def test_false_alarm_rate_under_no_change_is_bounded() -> None:
    # Calibration: 30 cases x 5 runs, 20% flaky, the agent unchanged. The verdict's
    # documented bound is 2 * alpha (per-case family + suite test); scripts/
    # measure_false_alarms.py reports the measured rate in docs/metrics.md.
    rng = random.Random(14)

    def sample(rates: list[float]) -> dict[str, CaseSummary]:
        return {
            f"c{i}": CaseSummary(sum(rng.random() < p for _ in range(5)), 5)
            for i, p in enumerate(rates)
        }

    trials = 400
    false_alarms = 0
    for _ in range(trials):
        rates = [1.0] * 22 + [0.0] * 2 + [rng.uniform(0.5, 0.95) for _ in range(6)]
        false_alarms += compare_runs(sample(rates), sample(rates)).verdict == "regression"
    assert false_alarms / trials <= 0.10
