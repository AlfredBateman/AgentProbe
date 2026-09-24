"""False-alarm rate of regression checks on flaky agents that did NOT change (SPEC.md §15).

    uv run python scripts/measure_false_alarms.py [--trials 5000] [--seed 20260924]

Each trial draws an agent (true per-case pass probabilities), runs it twice (baseline and
candidate) from the same probabilities, and asks each check whether it sees a regression. Any
alarm is false. The same checks then run on agents with a planted real regression, so a
check can't look good by never firing. Methodology and assumptions: docs/metrics.md.
Deterministic: the same arguments print the same tables.
"""

import argparse
import random
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

from agentprobe_core.stats import CaseSummary, compare_runs, wilson_interval
from agentprobe_core.suite.schema import StatisticsConfig

CONFIG = StatisticsConfig()  # the shipped defaults: alpha 0.05, min_drop 0.05
FLAKY_PASS_PROBABILITY = (0.5, 0.95)  # uniform range for flaky cases' true pass rate

Outcomes = list[list[bool]]  # [case][attempt]: did the attempt pass?


@dataclass(frozen=True)
class Scenario:
    name: str
    cases: int = 30
    runs: int = 5  # runs_per_case for the multi-run checks
    flaky_fraction: float = 0.2


REFERENCE = Scenario("reference")
SENSITIVITY = [
    REFERENCE,
    Scenario("5% flaky", flaky_fraction=0.05),
    Scenario("10% flaky", flaky_fraction=0.1),
    Scenario("40% flaky", flaky_fraction=0.4),
    Scenario("10 cases", cases=10),
    Scenario("100 cases", cases=100),
    Scenario("3 runs per case", runs=3),
    Scenario("10 runs per case", runs=10),
]


def draw_agent(scenario: Scenario, rng: random.Random) -> list[float]:
    """True pass probabilities: flaky cases first, then deterministic passes."""
    flaky = round(scenario.cases * scenario.flaky_fraction)
    return [rng.uniform(*FLAKY_PASS_PROBABILITY) for _ in range(flaky)] + [1.0] * (
        scenario.cases - flaky
    )


# Planted real regressions, applied to the candidate only. They change deterministic cases
# (at the end of the list), so the change isn't hidden inside existing flakiness.
REGRESSIONS: dict[str, Callable[[list[float]], list[float]]] = {
    "one case breaks (1 -> 0)": lambda p: [*p[:-1], 0.0],
    "three cases turn flaky (1 -> 0.5)": lambda p: [*p[:-3], 0.5, 0.5, 0.5],
    "every case 10% worse (p -> 0.9p)": lambda p: [0.9 * x for x in p],
}


def naive_single_run(baseline: Outcomes, candidate: Outcomes) -> bool:
    # One attempt per case; a case that passed on the baseline and fails now is a regression.
    return any(b[0] and not c[0] for b, c in zip(baseline, candidate, strict=True))


def single_run_with_retry(baseline: Outcomes, candidate: Outcomes) -> bool:
    # A failing attempt is retried once (pytest-rerunfailures style) on both runs.
    return any(
        (b[0] or b[1]) and not (c[0] or c[1]) for b, c in zip(baseline, candidate, strict=True)
    )


def multi_run_any_drop(baseline: Outcomes, candidate: Outcomes) -> bool:
    # More runs but no statistics: any case whose pass count went down.
    return any(sum(c) < sum(b) for b, c in zip(baseline, candidate, strict=True))


def multi_run_effect_only(baseline: Outcomes, candidate: Outcomes) -> bool:
    # min_drop without a significance test: the suite mean fell by at least min_drop.
    attempts = len(baseline) * len(baseline[0])
    drop = Fraction(sum(map(sum, baseline)) - sum(map(sum, candidate)), attempts)
    return drop >= Fraction(repr(CONFIG.min_drop))


def statistical(baseline: Outcomes, candidate: Outcomes) -> bool:
    # AgentProbe: Fisher + Holm per case, sign-flip permutation for the suite, and min_drop.
    def summarize(outcomes: Outcomes) -> dict[str, CaseSummary]:
        return {f"c{i}": CaseSummary(sum(o), len(o)) for i, o in enumerate(outcomes)}

    return compare_runs(summarize(baseline), summarize(candidate), CONFIG).verdict == "regression"


CHECKS: dict[str, tuple[str, Callable[[Outcomes, Outcomes], bool]]] = {
    "naive": ("Naive single run: any case pass -> fail", naive_single_run),
    "retry": ("Single run, failures retried once", single_run_with_retry),
    "any_drop": ("N runs, no statistics: any case's pass count fell", multi_run_any_drop),
    "effect": ("N runs, effect size only: suite mean fell >= min_drop", multi_run_effect_only),
    "statistical": ("N runs, AgentProbe statistical check", statistical),
}


def simulate(
    scenario: Scenario,
    regression: Callable[[list[float]], list[float]] | None,
    trials: int,
    seed: str,
) -> dict[str, int]:
    """Alarm counts per check. Every check sees the same simulated runs (the single-run
    checks use the first attempt, or the first two with a retry).
    """
    rng = random.Random(seed)  # noqa: S311 (seeded simulation, not crypto)
    alarms = dict.fromkeys(CHECKS, 0)
    for _ in range(trials):
        before = draw_agent(scenario, rng)
        after = regression(before) if regression else before
        baseline = [[rng.random() < p for _ in range(scenario.runs)] for p in before]
        candidate = [[rng.random() < p for _ in range(scenario.runs)] for p in after]
        for key, (_, check) in CHECKS.items():
            alarms[key] += check(baseline, candidate)
    return alarms


def percent(hits: int, trials: int) -> str:
    ci = wilson_interval(hits, trials)
    return f"{100 * hits / trials:.1f}% ({100 * ci.lower:.1f}-{100 * ci.upper:.1f})"


def reduction(naive: int, statistical: int, trials: int) -> str:
    """Relative reduction, with a conservative range from the two rates' 95% CIs."""
    if naive == 0:
        return "n/a (no naive false alarms)"
    n, s = wilson_interval(naive, trials), wilson_interval(statistical, trials)
    point = 1 - statistical / naive
    low, high = 1 - s.upper / n.lower, 1 - s.lower / n.upper
    return f"{100 * point:.1f}% ({100 * low:.1f}-{100 * high:.1f})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260924)
    args = parser.parse_args()
    trials, seed = args.trials, args.seed

    def run(scenario: Scenario, regression: str | None) -> dict[str, int]:
        planted = REGRESSIONS[regression] if regression else None
        return simulate(scenario, planted, trials, f"{seed}:{scenario.name}:{regression}")

    null = {s.name: run(s, None) for s in SENSITIVITY}
    power = {(s.name, r): run(s, r) for s in SENSITIVITY for r in REGRESSIONS}

    print(
        f"Trials per cell: {trials}, seed {seed}. Rates are % of trials with an alarm, "
        "with 95% Wilson intervals.\n"
    )
    print(
        f"## Reference scenario: {REFERENCE.cases} cases, {REFERENCE.runs} runs per case, "
        f"{REFERENCE.flaky_fraction:.0%} flaky\n"
    )
    print("| Check | False alarms (no change) | " + " | ".join(REGRESSIONS) + " |")
    print("|---|---|" + "---|" * len(REGRESSIONS))
    for key, (label, _) in CHECKS.items():
        cells = [percent(power[(REFERENCE.name, r)][key], trials) for r in REGRESSIONS]
        print(f"| {label} | {percent(null[REFERENCE.name][key], trials)} | {' | '.join(cells)} |")
    ref = null[REFERENCE.name]
    for key in ("naive", "retry"):
        print(
            f"\nFalse-alarm reduction, statistical vs {CHECKS[key][0].lower()}: "
            f"{reduction(ref[key], ref['statistical'], trials)}"
        )

    def label(s: Scenario) -> str:
        return f"{s.name} ({s.cases} cases, {s.runs} runs, {s.flaky_fraction:.0%} flaky)"

    print("\n## Sensitivity: false alarms (no change)\n")
    print("| Scenario | " + " | ".join(CHECKS[k][0] for k in CHECKS) + " | Reduction vs naive |")
    print("|---|" + "---|" * (len(CHECKS) + 1))
    for s in SENSITIVITY:
        fa = null[s.name]
        cells = " | ".join(percent(fa[k], trials) for k in CHECKS)
        print(f"| {label(s)} | {cells} | {reduction(fa['naive'], fa['statistical'], trials)} |")

    print("\n## Sensitivity: detection of planted regressions (naive / statistical)\n")
    print("| Scenario | " + " | ".join(REGRESSIONS) + " |")
    print("|---|" + "---|" * len(REGRESSIONS))
    for s in SENSITIVITY:
        detect = [
            f"{100 * power[(s.name, r)]['naive'] / trials:.1f}% / "
            f"{100 * power[(s.name, r)]['statistical'] / trials:.1f}%"
            for r in REGRESSIONS
        ]
        print(f"| {label(s)} | {' | '.join(detect)} |")


if __name__ == "__main__":
    main()
