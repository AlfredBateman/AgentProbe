"""False-alarm rates when nothing changed, by seeded simulation.

A verdict fires when the per-case family OR the suite test does, so `alpha` is split over
the two channels (ADR 0014 §Verdict). This checks all three rates across suite sizes,
flakiness levels and a suite where every case has its own true pass rate:

- each channel stays within `alpha` with confidence (the one-sided 97.5% Wilson upper bound
  of the measured rate, so a pass isn't luck of the seed);
- the **combined verdict** stays at or below `alpha`, which is the property the split buys.

The combined rate is measured, not derived: its worst cell measures about 2.9% against a
configured 5% (docs/metrics.md has the 5,000-trial numbers). Per cell the bar is the point
estimate, because at 1,000 trials a Wilson bound on a ~3% rate reaches ~4.8% and would make
the test a coin flip; the pooled bound over every cell supplies the confidence instead.

test_significance.py proves the per-case family's bound exactly, by enumeration, for small
families.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from agentprobe_core.stats import CaseSummary, compare_runs, wilson_interval
from agentprobe_core.suite.schema import StatisticsConfig

CONFIG = StatisticsConfig()
ALPHA = CONFIG.alpha
TRIALS = 1_000
SIZES = (5, 13, 30, 100)


def _flaky(fraction: float) -> Callable[[random.Random, int], list[float]]:
    # A `fraction` of cases flaky with a true pass rate drawn from U(0.5, 0.95), the rest
    # deterministic passes (as in scripts/measure_false_alarms.py).
    def rates(rng: random.Random, size: int) -> list[float]:
        flaky = round(size * fraction)
        return [rng.uniform(0.5, 0.95) for _ in range(flaky)] + [1.0] * (size - flaky)

    return rates


SCENARIOS: dict[str, Callable[[random.Random, int], list[float]]] = {
    "20% flaky": _flaky(0.2),
    "50% flaky": _flaky(0.5),
    "all flaky": _flaky(1.0),
    # Every case its own true pass rate, evenly spread over 0.05..0.95.
    "different rates": lambda _, size: [0.05 + 0.9 * i / max(size - 1, 1) for i in range(size)],
    "all coin flips": lambda _, size: [0.5] * size,  # the most variable a case can be
}


@dataclass(frozen=True)
class Alarms:
    """How often each channel, and the verdict, fired on an agent that didn't change."""

    cases: int  # the per-case family (Tarone-Holm at alpha_cases)
    suite: int  # the sign-flip suite test (at alpha_suite)
    verdict: int  # either one: what a CI gate acts on

    def rate(self, channel: str) -> float:
        return getattr(self, channel) / TRIALS

    def upper(self, channel: str) -> float:
        return wilson_interval(getattr(self, channel), TRIALS).upper


def _run(rng: random.Random, rates: list[float], attempts: int) -> dict[str, CaseSummary]:
    return {
        f"c{i}": CaseSummary(sum(rng.random() < p for _ in range(attempts)), attempts)
        for i, p in enumerate(rates)
    }


def _alarms(scenario: str, size: int, attempts: int) -> Alarms:
    rng = random.Random(f"fwer:{scenario}:{size}:{attempts}")
    cases = suite = verdict = 0
    for _ in range(TRIALS):
        rates = SCENARIOS[scenario](rng, size)  # the agent: same in both runs
        report = compare_runs(_run(rng, rates, attempts), _run(rng, rates, attempts), CONFIG)
        cases += bool(report.regressed)
        suite += report.suite is not None and report.suite.regressed
        verdict += report.verdict == "regression"
    return Alarms(cases, suite, verdict)


@pytest.fixture(scope="module")
def grid() -> dict[tuple[str, int], Alarms]:
    """Every cell of the calibration grid, simulated once for the tests below."""
    return {(s, n): _alarms(s, n, attempts=5) for s in SCENARIOS for n in SIZES}


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_verdict_false_alarm_rate_is_at_most_alpha(
    grid: dict[tuple[str, int], Alarms], scenario: str, size: int
) -> None:
    alarms = grid[(scenario, size)]
    assert alarms.rate("verdict") <= ALPHA, (
        f"{alarms.verdict}/{TRIALS} verdicts on an unchanged agent "
        f"(per-case {alarms.cases}, suite {alarms.suite})"
    )


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("scenario", list(SCENARIOS))
@pytest.mark.parametrize("channel", ["cases", "suite"])
def test_each_channel_stays_within_alpha(
    grid: dict[tuple[str, int], Alarms], channel: str, scenario: str, size: int
) -> None:
    # Each channel's own budget is alpha / 2; this asserts the weaker bound that holds with
    # confidence at 1,000 trials. Their measured shares are in docs/metrics.md.
    alarms = grid[(scenario, size)]
    assert alarms.upper(channel) <= ALPHA, (
        f"{getattr(alarms, channel)}/{TRIALS} {channel} false alarms, "
        f"upper bound {alarms.upper(channel):.4f}"
    )


def test_pooled_verdict_rate_is_below_alpha_with_confidence(
    grid: dict[tuple[str, int], Alarms],
) -> None:
    """The whole grid pooled: enough trials for the Wilson bound to be tight, so the split's
    guarantee is checked with confidence and not only cell by cell.
    """
    alarms = sum(cell.verdict for cell in grid.values())
    trials = TRIALS * len(grid)
    upper = wilson_interval(alarms, trials).upper
    assert upper <= ALPHA, f"{alarms}/{trials} verdicts, upper bound {upper:.4f}"


@pytest.mark.parametrize("attempts", [3, 10])
@pytest.mark.parametrize("scenario", ["different rates", "all coin flips"])
def test_false_alarm_rates_at_other_run_counts(scenario: str, attempts: int) -> None:
    alarms = _alarms(scenario, 30, attempts)
    assert alarms.rate("verdict") <= ALPHA, f"{alarms.verdict}/{TRIALS} verdicts"
    assert alarms.upper("cases") <= ALPHA, f"{alarms.cases}/{TRIALS} per-case false alarms"
    assert alarms.upper("suite") <= ALPHA, f"{alarms.suite}/{TRIALS} suite false alarms"
