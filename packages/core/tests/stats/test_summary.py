import random
import statistics

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agentprobe_core.stats import CaseSummary, suite_stats, wilson_interval
from agentprobe_core.stats.summary import _quantile


@st.composite
def counts(draw: st.DrawFn, max_attempts: int = 20) -> tuple[int, int]:
    attempts = draw(st.integers(1, max_attempts))
    return draw(st.integers(0, attempts)), attempts


summaries = counts().map(lambda c: CaseSummary(passes=c[0], attempts=c[1]))


# --- CaseSummary and labels ---


@pytest.mark.parametrize(
    ("passes", "attempts", "errors"),
    [(0, 0, 0), (-1, 5, 0), (6, 5, 0), (3, 5, 3), (2, 5, -1)],
)
def test_case_summary_rejects_impossible_counts(passes: int, attempts: int, errors: int) -> None:
    with pytest.raises(ValueError):
        CaseSummary(passes=passes, attempts=attempts, errors=errors)


@pytest.mark.parametrize(
    ("passes", "attempts", "errors", "label"),
    [
        (5, 5, 0, "stable-pass"),
        (0, 5, 0, "stable-fail"),
        (0, 5, 5, "stable-fail"),  # every attempt errored
        (3, 5, 0, "flaky"),
        (3, 5, 2, "flaky"),  # errors count as non-passes
        (1, 1, 0, "stable-pass"),  # one attempt can never be flaky
        (0, 1, 0, "stable-fail"),
    ],
)
def test_label_rule(passes: int, attempts: int, errors: int, label: str) -> None:
    summary = CaseSummary(passes=passes, attempts=attempts, errors=errors)
    assert summary.label == label


@given(summaries)
def test_label_matches_pass_rate(summary: CaseSummary) -> None:
    expected = {1.0: "stable-pass", 0.0: "stable-fail"}.get(summary.pass_rate, "flaky")
    assert summary.label == expected


# --- Wilson interval ---


@pytest.mark.parametrize(
    ("passes", "attempts", "lower", "upper"),
    [
        # Newcombe (1998), Statistics in Medicine 17:857-872, Table I, method 3 (score).
        (81, 263, 0.2553, 0.3662),
        (15, 148, 0.0624, 0.1605),
        (0, 20, 0.0, 0.1611),
        (1, 29, 0.0061, 0.1718),
        # Closed forms: at 0/n the upper bound is z^2 / (n + z^2); at n/n the lower bound
        # is n / (n + z^2).
        (0, 10, 0.0, 0.2775),
        (5, 5, 0.5655, 1.0),
        (5, 10, 0.2366, 0.7634),
    ],
)
def test_wilson_known_answers(passes: int, attempts: int, lower: float, upper: float) -> None:
    interval = wilson_interval(passes, attempts)
    assert interval.lower == pytest.approx(lower, abs=5e-5)
    assert interval.upper == pytest.approx(upper, abs=5e-5)


def test_wilson_other_confidence_level() -> None:
    # 0/n upper bound = z^2 / (n + z^2) with z = 2.5758 at 99%.
    z = statistics.NormalDist().inv_cdf(0.995)
    assert wilson_interval(0, 10, 0.99).upper == pytest.approx(z * z / (10 + z * z))


@pytest.mark.parametrize("confidence", [0.0, 1.0, -0.5, 1.5])
def test_wilson_rejects_bad_confidence(confidence: float) -> None:
    with pytest.raises(ValueError):
        wilson_interval(1, 2, confidence)


@pytest.mark.parametrize(("passes", "attempts"), [(0, 0), (3, 2), (-1, 2)])
def test_wilson_rejects_bad_counts(passes: int, attempts: int) -> None:
    with pytest.raises(ValueError):
        wilson_interval(passes, attempts)


@given(counts(max_attempts=500))
def test_wilson_contains_estimate_within_unit_interval(c: tuple[int, int]) -> None:
    passes, attempts = c
    interval = wilson_interval(passes, attempts)
    assert 0.0 <= interval.lower <= passes / attempts <= interval.upper <= 1.0
    assert (interval.lower == 0.0) == (passes == 0)
    assert (interval.upper == 1.0) == (passes == attempts)


@given(counts(max_attempts=500))
def test_wilson_is_symmetric_in_passes_and_failures(c: tuple[int, int]) -> None:
    passes, attempts = c
    interval = wilson_interval(passes, attempts)
    mirrored = wilson_interval(attempts - passes, attempts)
    assert interval.lower == pytest.approx(1 - mirrored.upper, abs=1e-12)
    assert interval.upper == pytest.approx(1 - mirrored.lower, abs=1e-12)


@given(counts(max_attempts=200), st.floats(0.5, 0.98))
def test_wilson_narrows_with_more_data_and_widens_with_confidence(
    c: tuple[int, int], confidence: float
) -> None:
    passes, attempts = c
    base = wilson_interval(passes, attempts, confidence)
    more_data = wilson_interval(2 * passes, 2 * attempts, confidence)
    more_confident = wilson_interval(passes, attempts, confidence + 0.01)
    width = base.upper - base.lower
    assert more_data.upper - more_data.lower < width
    assert more_confident.upper - more_confident.lower > width


# --- Suite pass rate and bootstrap CI ---


def test_quantile_matches_stdlib_inclusive_method() -> None:
    values = sorted(random.Random(1).random() for _ in range(999))
    cuts = statistics.quantiles(values, n=40, method="inclusive")
    assert _quantile(values, 1 / 40) == pytest.approx(cuts[0])
    assert _quantile(values, 39 / 40) == pytest.approx(cuts[-1])
    assert _quantile(values, 0.0) == values[0]
    assert _quantile(values, 1.0) == values[-1]


def test_suite_rate_is_mean_of_case_rates_not_pooled_attempts() -> None:
    stats = suite_stats([CaseSummary(passes=1, attempts=1), CaseSummary(passes=0, attempts=9)])
    assert stats.pass_rate == 0.5  # pooled would be 0.1
    assert stats.cases == 2
    assert stats.attempts == 10


def test_bootstrap_matches_binomial_quantiles_for_split_suite() -> None:
    # 10 stable-pass + 10 stable-fail cases: a resampled mean is Binomial(20, 0.5) / 20, whose
    # 2.5% / 97.5% quantiles are 6/20 and 14/20.
    cases = [CaseSummary(5, 5)] * 10 + [CaseSummary(0, 5)] * 10
    stats = suite_stats(cases)
    assert stats.ci.lower == pytest.approx(0.30, abs=0.02)
    assert stats.ci.upper == pytest.approx(0.70, abs=0.02)
    # Why the case is the resampling unit: pooled-attempt Wilson treats the 100 attempts as
    # independent and is less than half as wide.
    pooled = wilson_interval(50, 100)
    assert pooled.upper - pooled.lower < (stats.ci.upper - stats.ci.lower) / 2


def test_single_case_suite_ci_is_that_cases_wilson_interval() -> None:
    case = CaseSummary(passes=3, attempts=5)
    assert suite_stats([case]).ci == case.wilson()


def test_zero_variance_suite_gets_binomial_floor_not_a_point() -> None:
    # Every case stable-pass: every resample has mean 1.0, but 100 attempts still leave
    # binomial uncertainty, so the CI is the Wilson interval for 100/100.
    stats = suite_stats([CaseSummary(5, 5)] * 20)
    assert stats.pass_rate == 1.0
    assert stats.ci == wilson_interval(100, 100)
    assert stats.ci.lower < 0.97


def test_floor_uses_effective_sample_size_for_unequal_attempts() -> None:
    # Two cases at rate 0.5 with 2 and 18 attempts: n_eff = 2^2 / (1/2 + 1/18) = 7.2.
    # The bootstrap is degenerate (both rates 0.5), so the CI is Wilson at p = 0.5, n = 7.2,
    # which is centered on 0.5.
    stats = suite_stats([CaseSummary(1, 2), CaseSummary(9, 18)])
    z = statistics.NormalDist().inv_cdf(0.975)
    n = 7.2
    half = z * (0.25 / n + z * z / (4 * n * n)) ** 0.5 / (1 + z * z / n)
    assert stats.ci.lower == pytest.approx(0.5 - half)
    assert stats.ci.upper == pytest.approx(0.5 + half)


def test_suite_stats_is_deterministic_for_a_seed() -> None:
    cases = [CaseSummary(p, 5) for p in (5, 4, 3, 5, 0, 2, 5, 1)]
    assert suite_stats(cases, seed=7) == suite_stats(cases, seed=7)
    assert suite_stats(cases, seed=7).ci != suite_stats(cases, seed=8).ci


def test_suite_stats_rejects_empty_suite_and_bad_resamples() -> None:
    with pytest.raises(ValueError):
        suite_stats([])
    with pytest.raises(ValueError):
        suite_stats([CaseSummary(1, 1)], resamples=0)


@given(st.lists(summaries, min_size=1, max_size=30), st.integers(0, 2**32))
def test_suite_ci_contains_estimate_within_unit_interval(
    cases: list[CaseSummary], seed: int
) -> None:
    stats = suite_stats(cases, resamples=200, seed=seed)
    assert 0.0 <= stats.ci.lower <= stats.pass_rate <= stats.ci.upper <= 1.0
    assert stats.ci.lower < stats.ci.upper  # never a zero-width interval


def test_suite_ci_coverage_is_near_nominal() -> None:
    # Draw a fresh 30-case suite from a known population of case pass rates each time and
    # check how often the 95% CI covers the population mean. The percentile bootstrap runs
    # slightly under nominal with few clusters (ADR 0014); it must not be far under.
    rng = random.Random(2026)
    population = [1.0] * 60 + [0.0] * 10 + [round(0.3 + 0.6 * i / 29, 3) for i in range(30)]
    true_mean = statistics.fmean(population)
    covered = 0
    simulations = 300
    for index in range(simulations):
        rates = rng.choices(population, k=30)
        cases = [CaseSummary(sum(rng.random() < p for _ in range(5)), 5) for p in rates]
        ci = suite_stats(cases, resamples=500, seed=index).ci
        covered += ci.lower <= true_mean <= ci.upper
    assert 0.90 <= covered / simulations <= 0.99
