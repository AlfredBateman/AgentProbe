"""False-alarm rate of regression checks on flaky agents that did NOT change (SPEC.md §15).

    uv run python scripts/measure_false_alarms.py [--trials 5000] [--grid-trials 1000]
                                                  [--seed 20260924]

Each trial draws an agent (true per-case pass probabilities), runs it twice (baseline and
candidate) from the same probabilities, and asks each check whether it sees a regression. Any
alarm is false. The same checks then run on agents with a planted real regression, so a
check can't look good by never firing. The statistical check is shown with Tarone-Holm (what
ships) and with plain Holm (before ADR 0014's amendment). A last grid breaks the statistical
check's false alarms down into the per-case family and the whole verdict. Methodology and
assumptions: docs/metrics.md. Deterministic: the same arguments print the same tables.
"""

import argparse
import random
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

from agentprobe_core.stats import (
    CaseSummary,
    RegressionReport,
    compare_runs,
    fisher_exact,
    tarone_holm,
    wilson_interval,
)
from agentprobe_core.suite.schema import StatisticsConfig

CONFIG = StatisticsConfig()  # the shipped defaults: alpha 0.05, min_drop 0.05
ALPHA, MIN_DROP = Fraction(repr(CONFIG.alpha)), Fraction(repr(CONFIG.min_drop))
FLAKY_PASS_PROBABILITY = (0.5, 0.95)  # uniform range for flaky cases' true pass rate

Outcomes = list[list[bool]]  # [case][attempt]: did the attempt pass?
Summaries = dict[str, CaseSummary]


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


@dataclass(frozen=True)
class Trial:
    baseline: Outcomes
    candidate: Outcomes
    summaries: tuple[Summaries, Summaries]
    report: RegressionReport  # AgentProbe's compare_runs on the multi-run data


def summarize(outcomes: Outcomes) -> Summaries:
    return {f"c{i}": CaseSummary(sum(o), len(o)) for i, o in enumerate(outcomes)}


def naive_single_run(trial: Trial) -> bool:
    # One attempt per case; a case that passed on the baseline and fails now is a regression.
    return any(b[0] and not c[0] for b, c in zip(trial.baseline, trial.candidate, strict=True))


def single_run_with_retry(trial: Trial) -> bool:
    # A failing attempt is retried once (pytest-rerunfailures style) on both runs.
    return any(
        (b[0] or b[1]) and not (c[0] or c[1])
        for b, c in zip(trial.baseline, trial.candidate, strict=True)
    )


def multi_run_any_drop(trial: Trial) -> bool:
    # More runs but no statistics: any case whose pass count went down.
    return any(sum(c) < sum(b) for b, c in zip(trial.baseline, trial.candidate, strict=True))


def multi_run_effect_only(trial: Trial) -> bool:
    # min_drop without a significance test: the suite mean fell by at least min_drop.
    attempts = len(trial.baseline) * len(trial.baseline[0])
    drop = sum(map(sum, trial.baseline)) - sum(map(sum, trial.candidate))
    return Fraction(drop, attempts) >= MIN_DROP


def statistical_holm(trial: Trial) -> bool:
    # The same check with plain Holm per case: Tarone-Holm with every minimum p at 0 is
    # exactly Holm (tested). The suite-level test is unchanged.
    baseline, candidate = trial.summaries
    fisher = [fisher_exact(baseline[c], candidate[c]) for c in baseline]
    holm = tarone_holm([f.p_worse for f in fisher], [Fraction(0)] * len(fisher), ALPHA)
    per_case = any(
        decision.rejected
        and Fraction(b.passes, b.attempts) - Fraction(c.passes, c.attempts) >= MIN_DROP
        for decision, b, c in zip(holm, baseline.values(), candidate.values(), strict=True)
    )
    return per_case or (trial.report.suite is not None and trial.report.suite.regressed)


def statistical(trial: Trial) -> bool:
    # AgentProbe as shipped: Fisher + Tarone-Holm per case, sign-flip permutation for the
    # suite, and min_drop on both.
    return trial.report.verdict == "regression"


CHECKS: dict[str, tuple[str, Callable[[Trial], bool]]] = {
    "naive": ("Naive single run: any case pass -> fail", naive_single_run),
    "retry": ("Single run, failures retried once", single_run_with_retry),
    "any_drop": ("N runs, no statistics: any case's pass count fell", multi_run_any_drop),
    "effect": ("N runs, effect size only: suite mean fell >= min_drop", multi_run_effect_only),
    "holm": ("N runs, statistical, Holm per case (before)", statistical_holm),
    "statistical": ("N runs, statistical, Tarone-Holm per case (shipped)", statistical),
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
        summaries = summarize(baseline), summarize(candidate)
        report = compare_runs(*summaries, CONFIG)
        trial = Trial(baseline, candidate, summaries, report)
        for key, (_, check) in CHECKS.items():
            alarms[key] += check(trial)
    return alarms


# Null calibration grid, the same scenarios as packages/core/tests/stats/
# test_family_wise_error.py (which asserts the per-case family's bound).
GRID_SIZES = (5, 13, 30, 100)
GRID_SCENARIOS: dict[str, Callable[[random.Random, int], list[float]]] = {
    "20% flaky": lambda rng, n: draw_agent(Scenario("", n, flaky_fraction=0.2), rng),
    "50% flaky": lambda rng, n: draw_agent(Scenario("", n, flaky_fraction=0.5), rng),
    "all flaky": lambda rng, n: draw_agent(Scenario("", n, flaky_fraction=1.0), rng),
    "different rates": lambda _, n: [0.05 + 0.9 * i / max(n - 1, 1) for i in range(n)],
    "all coin flips": lambda _, n: [0.5] * n,
}


def calibrate(scenario: str, size: int, trials: int, seed: str) -> tuple[int, int]:
    """(per-case family alarms, verdict alarms) with nothing changed, at 5 runs per case."""
    rng = random.Random(seed)  # noqa: S311 (seeded simulation, not crypto)
    family = verdict = 0
    for _ in range(trials):
        rates = GRID_SCENARIOS[scenario](rng, size)
        runs = [
            {
                f"c{i}": CaseSummary(sum(rng.random() < p for _ in range(5)), 5)
                for i, p in enumerate(rates)
            }
            for _ in range(2)
        ]
        report = compare_runs(runs[0], runs[1], CONFIG)
        family += bool(report.regressed)
        verdict += report.verdict == "regression"
    return family, verdict


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
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--grid-trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260924)
    args = parser.parse_args()
    trials, seed = args.trials, args.seed

    def run(scenario: Scenario, regression: str | None) -> dict[str, int]:
        planted = REGRESSIONS[regression] if regression else None
        return simulate(scenario, planted, trials, f"{seed}:{scenario.name}:{regression}")

    null = {s.name: run(s, None) for s in SENSITIVITY}
    power = {(s.name, r): run(s, r) for s in SENSITIVITY for r in REGRESSIONS}

    def label(s: Scenario) -> str:
        return f"{s.name} ({s.cases} cases, {s.runs} runs, {s.flaky_fraction:.0%} flaky)"

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
    for key, (name, _) in CHECKS.items():
        cells = [percent(power[(REFERENCE.name, r)][key], trials) for r in REGRESSIONS]
        print(f"| {name} | {percent(null[REFERENCE.name][key], trials)} | {' | '.join(cells)} |")
    ref = null[REFERENCE.name]
    for check in ("statistical", "holm"):
        for key in ("naive", "retry"):
            print(
                f"\nFalse-alarm reduction, {CHECKS[check][0].lower()} vs "
                f"{CHECKS[key][0].lower()}: {reduction(ref[key], ref[check], trials)}"
            )

    print("\n## With and without Tarone\n")
    print(
        "| Scenario | Naive FA | Holm FA | Tarone-Holm FA | Reduction vs naive, Holm "
        "| Reduction vs naive, Tarone-Holm | One case breaks: naive / Holm / Tarone-Holm |"
    )
    print("|---|---|---|---|---|---|---|")
    single_break = next(iter(REGRESSIONS))
    for s in SENSITIVITY:
        fa, hits = null[s.name], power[(s.name, single_break)]
        detect = " / ".join(
            f"{100 * hits[k] / trials:.1f}%" for k in ("naive", "holm", "statistical")
        )
        print(
            f"| {label(s)} | {percent(fa['naive'], trials)} | {percent(fa['holm'], trials)} "
            f"| {percent(fa['statistical'], trials)} "
            f"| {reduction(fa['naive'], fa['holm'], trials)} "
            f"| {reduction(fa['naive'], fa['statistical'], trials)} | {detect} |"
        )

    print("\n## Sensitivity: false alarms (no change)\n")
    print("| Scenario | " + " | ".join(CHECKS[k][0] for k in CHECKS) + " |")
    print("|---|" + "---|" * len(CHECKS))
    for s in SENSITIVITY:
        cells = " | ".join(percent(null[s.name][k], trials) for k in CHECKS)
        print(f"| {label(s)} | {cells} |")

    print("\n## Sensitivity: detection of planted regressions (naive / Holm / Tarone-Holm)\n")
    print("| Scenario | " + " | ".join(REGRESSIONS) + " |")
    print("|---|" + "---|" * len(REGRESSIONS))
    for s in SENSITIVITY:
        detect = [
            " / ".join(
                f"{100 * power[(s.name, r)][k] / trials:.1f}%"
                for k in ("naive", "holm", "statistical")
            )
            for r in REGRESSIONS
        ]
        print(f"| {label(s)} | {' | '.join(detect)} |")

    grid_trials = args.grid_trials
    print(
        f"\n## Null calibration: per-case family vs whole verdict ({grid_trials} trials per "
        "cell, 5 runs per case)\n"
    )
    print("| Scenario | Cases | Per-case family (Tarone-Holm) | Verdict (family + suite test) |")
    print("|---|---|---|---|")
    for name in GRID_SCENARIOS:
        for size in GRID_SIZES:
            family, verdict = calibrate(name, size, grid_trials, f"{seed}:grid:{name}:{size}")
            print(
                f"| {name} | {size} | {percent(family, grid_trials)} "
                f"| {percent(verdict, grid_trials)} |"
            )


if __name__ == "__main__":
    main()
