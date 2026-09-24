"""Regression detection between a baseline run and a candidate run (SPEC.md §4.6-4.7,
ADR 0006, ADR 0014).

A drop is flagged only when it is statistically significant at `alpha` AND at least
`min_drop`, per case (Fisher exact, Holm-corrected) or for the suite (paired sign-flip
permutation test on the cases both runs share). Rises are flagged the same way.
"""

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from statistics import fmean
from typing import Literal

from agentprobe_core.stats.significance import fisher_exact, holm, sign_flip_test
from agentprobe_core.stats.summary import DEFAULT_SEED, CaseSummary
from agentprobe_core.suite.schema import StatisticsConfig

Verdict = Literal["regression", "no_change", "improvement"]


@dataclass(frozen=True)
class MetricDelta:
    baseline: float
    candidate: float
    delta: float  # candidate - baseline


@dataclass(frozen=True)
class CaseComparison:
    case_id: str
    baseline: CaseSummary
    candidate: CaseSummary
    pass_rate_delta: float  # candidate - baseline
    p_worse: float  # one-sided Fisher exact, uncorrected
    p_worse_adjusted: float  # Holm-corrected across the compared cases
    p_better: float
    p_better_adjusted: float
    regressed: bool
    improved: bool
    score_delta: float | None
    latency_delta_ms: float | None
    cost_per_attempt_delta_usd: float | None


@dataclass(frozen=True)
class SuiteComparison:
    """Over the cases both runs share, so adding or removing cases never looks like a change."""

    cases: int
    baseline_pass_rate: float
    candidate_pass_rate: float
    pass_rate_delta: float
    p_worse: float  # one-sided sign-flip permutation test
    p_better: float
    exact: bool  # False: Monte Carlo p-values
    regressed: bool
    improved: bool
    score: MetricDelta | None  # mean over cases of each case's mean score
    latency_ms: MetricDelta | None  # mean over cases of each case's mean latency
    cost_usd: MetricDelta | None  # one attempt of every case: sum of per-attempt costs


@dataclass(frozen=True)
class RegressionReport:
    verdict: Verdict
    alpha: float
    min_drop: float
    suite: SuiteComparison | None  # None when the runs share no case
    cases: list[CaseComparison]  # shared cases, in baseline order
    regressed: list[str]  # statistically flagged, per case
    improved: list[str]
    # Label transitions: descriptive, not tested for significance. A case can be in two
    # lists (flaky -> stable-fail is newly failing and no longer flaky).
    newly_failing: list[str]  # stable-fail now, not before
    newly_passing: list[str]  # stable-pass now, not before
    newly_flaky: list[str]  # flaky now, not before
    no_longer_flaky: list[str]  # flaky before, not now
    added: list[str]  # only in the candidate: not compared
    removed: list[str]  # only in the baseline: not compared


def compare_runs(
    baseline: Mapping[str, CaseSummary],
    candidate: Mapping[str, CaseSummary],
    config: StatisticsConfig | None = None,
    *,
    seed: int = DEFAULT_SEED,
) -> RegressionReport:
    """Compares two runs keyed by case id.

    Verdict: `regression` if any case or the suite is flagged worse (this wins over any
    improvement, since it's what a CI gate must catch), else `improvement` if any case or
    the suite is flagged better, else `no_change`. The per-case family and the suite test
    each hold their false-alarm rate at alpha, so the verdict's worst case is 2 * alpha
    (union bound); docs/metrics.md measures the actual rate.

    Power is limited at small N: with 5 attempts per case the smallest possible per-case
    p-value is 1/252, which Holm can't bring under 0.05 once 13+ cases are compared (ADR 0014).
    """
    config = config if config is not None else StatisticsConfig()
    alpha = _exact(config.alpha)
    min_drop = _exact(config.min_drop)
    shared = [case_id for case_id in baseline if case_id in candidate]

    deltas = [_rate(candidate[c]) - _rate(baseline[c]) for c in shared]
    fisher = [fisher_exact(baseline[c], candidate[c]) for c in shared]
    worse_adjusted = holm([p_worse for p_worse, _ in fisher])
    better_adjusted = holm([p_better for _, p_better in fisher])
    cases = [
        _compare_case(
            case_id,
            baseline[case_id],
            candidate[case_id],
            delta,
            fisher[i],
            (worse_adjusted[i], better_adjusted[i]),
            alpha,
            min_drop,
        )
        for i, (case_id, delta) in enumerate(zip(shared, deltas, strict=True))
    ]

    suite = None
    if shared:
        test = sign_flip_test(deltas, draws=config.permutation_draws, seed=seed)
        mean_delta = sum(deltas, Fraction(0)) / len(deltas)
        pairs = [(baseline[c], candidate[c]) for c in shared]
        suite = SuiteComparison(
            cases=len(shared),
            baseline_pass_rate=fmean(b.pass_rate for b, _ in pairs),
            candidate_pass_rate=fmean(c.pass_rate for _, c in pairs),
            pass_rate_delta=float(mean_delta),
            p_worse=float(test.p_worse),
            p_better=float(test.p_better),
            exact=test.exact,
            regressed=test.p_worse <= alpha and -mean_delta >= min_drop,
            improved=test.p_better <= alpha and mean_delta >= min_drop,
            score=_aggregate(pairs, lambda s: s.mean_score, fmean),
            latency_ms=_aggregate(pairs, lambda s: s.mean_latency_ms, fmean),
            cost_usd=_aggregate(pairs, _cost_per_attempt, math.fsum),
        )

    regressed = [c.case_id for c in cases if c.regressed]
    improved = [c.case_id for c in cases if c.improved]
    verdict: Verdict = "no_change"
    if regressed or (suite is not None and suite.regressed):
        verdict = "regression"
    elif improved or (suite is not None and suite.improved):
        verdict = "improvement"

    def became(label: str) -> list[str]:
        return [c for c in shared if candidate[c].label == label and baseline[c].label != label]

    return RegressionReport(
        verdict=verdict,
        alpha=config.alpha,
        min_drop=config.min_drop,
        suite=suite,
        cases=cases,
        regressed=regressed,
        improved=improved,
        newly_failing=became("stable-fail"),
        newly_passing=became("stable-pass"),
        newly_flaky=became("flaky"),
        no_longer_flaky=[
            c for c in shared if baseline[c].label == "flaky" and candidate[c].label != "flaky"
        ],
        added=[c for c in candidate if c not in baseline],
        removed=[c for c in baseline if c not in candidate],
    )


def _compare_case(
    case_id: str,
    baseline: CaseSummary,
    candidate: CaseSummary,
    delta: Fraction,
    p_values: tuple[Fraction, Fraction],
    adjusted: tuple[Fraction, Fraction],
    alpha: Fraction,
    min_drop: Fraction,
) -> CaseComparison:
    return CaseComparison(
        case_id=case_id,
        baseline=baseline,
        candidate=candidate,
        pass_rate_delta=float(delta),
        p_worse=float(p_values[0]),
        p_worse_adjusted=float(adjusted[0]),
        p_better=float(p_values[1]),
        p_better_adjusted=float(adjusted[1]),
        regressed=adjusted[0] <= alpha and -delta >= min_drop,
        improved=adjusted[1] <= alpha and delta >= min_drop,
        score_delta=_difference(baseline.mean_score, candidate.mean_score),
        latency_delta_ms=_difference(baseline.mean_latency_ms, candidate.mean_latency_ms),
        cost_per_attempt_delta_usd=_difference(
            _cost_per_attempt(baseline), _cost_per_attempt(candidate)
        ),
    )


def _exact(value: float) -> Fraction:
    # The decimal the user wrote (0.05 -> 1/20), not the binary float's expansion (slightly
    # more than 1/20), so a drop of exactly min_drop, or p = alpha, compares as equal.
    return Fraction(repr(value))


def _rate(summary: CaseSummary) -> Fraction:
    return Fraction(summary.passes, summary.attempts)


def _cost_per_attempt(summary: CaseSummary) -> float | None:
    # Per attempt, so runs with different runs_per_case compare fairly.
    return None if summary.cost_usd is None else summary.cost_usd / summary.attempts


def _difference(baseline: float | None, candidate: float | None) -> float | None:
    return None if baseline is None or candidate is None else candidate - baseline


def _aggregate(
    pairs: list[tuple[CaseSummary, CaseSummary]],
    metric: Callable[[CaseSummary], float | None],
    combine: Callable[[Iterable[float]], float],
) -> MetricDelta | None:
    """Combines a metric over the shared cases where both runs report it."""
    known: list[tuple[float, float]] = []
    for baseline, candidate in pairs:
        pair = metric(baseline), metric(candidate)
        if pair[0] is not None and pair[1] is not None:
            known.append((pair[0], pair[1]))
    if not known:
        return None
    before = combine(b for b, _ in known)
    after = combine(c for _, c in known)
    return MetricDelta(baseline=before, candidate=after, delta=after - before)
