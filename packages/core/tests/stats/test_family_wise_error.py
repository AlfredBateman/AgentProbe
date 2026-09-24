"""The per-case family's false-alarm rate when nothing changed, by seeded simulation.

Tarone-Holm on one-sided Fisher tests promises family-wise error <= alpha (ADR 0014); this
checks it across suite sizes, flakiness levels and a suite where every case has its own
true pass rate. The bar is the one-sided 97.5% Wilson upper bound of the measured rate, not
the point estimate, so a pass means the rate is below alpha with confidence, not by luck of
the seed. test_significance.py proves the same bound exactly, by enumeration, for small
families.
"""

import random
from collections.abc import Callable

import pytest

from agentprobe_core.stats import CaseSummary, compare_cases, wilson_interval
from agentprobe_core.suite.schema import StatisticsConfig

ALPHA = StatisticsConfig().alpha
TRIALS = 1_000


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


def _run(rng: random.Random, rates: list[float], attempts: int) -> dict[str, CaseSummary]:
    return {
        f"c{i}": CaseSummary(sum(rng.random() < p for _ in range(attempts)), attempts)
        for i, p in enumerate(rates)
    }


def _false_alarms(scenario: str, size: int, attempts: int) -> int:
    rng = random.Random(f"fwer:{scenario}:{size}:{attempts}")
    alarms = 0
    for _ in range(TRIALS):
        rates = SCENARIOS[scenario](rng, size)  # the agent: same in both runs
        cases = compare_cases(_run(rng, rates, attempts), _run(rng, rates, attempts))
        alarms += any(case.regressed for case in cases)
    return alarms


@pytest.mark.parametrize("size", [5, 13, 30, 100])
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_family_wise_false_alarm_rate_is_at_most_alpha(scenario: str, size: int) -> None:
    alarms = _false_alarms(scenario, size, attempts=5)
    upper = wilson_interval(alarms, TRIALS).upper
    assert upper <= ALPHA, f"{alarms}/{TRIALS} false alarms, upper bound {upper:.4f}"


@pytest.mark.parametrize("attempts", [3, 10])
@pytest.mark.parametrize("scenario", ["different rates", "all coin flips"])
def test_family_wise_false_alarm_rate_at_other_run_counts(scenario: str, attempts: int) -> None:
    alarms = _false_alarms(scenario, 30, attempts)
    upper = wilson_interval(alarms, TRIALS).upper
    assert upper <= ALPHA, f"{alarms}/{TRIALS} false alarms, upper bound {upper:.4f}"
