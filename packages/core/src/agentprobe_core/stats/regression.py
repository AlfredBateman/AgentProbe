"""Regression detection between a baseline run and a candidate run (SPEC.md §4.6-4.7,
ADR 0006, ADR 0014).

A drop is flagged only when it is statistically significant AND at least `min_drop`: per
case (one-sided Fisher exact, Tarone-Holm step-down across the shared cases) or for the
suite (paired sign-flip permutation test on the shared cases). Rises are flagged the same
way, as a separate family.

Either channel firing is a regression, so `alpha` is split between them (`alpha_cases` and
`alpha_suite`, half each by default). Each channel holds its own rate at its share, so the
verdict's rate is at most their sum, which is `alpha` (ADR 0014 §Verdict).
"""

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from statistics import fmean
from typing import Literal

from agentprobe_core.stats.significance import (
    StepDownDecision,
    fisher_exact,
    sign_flip_test,
    tarone_holm,
)
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
    """One shared case. There are no "adjusted p-values": Tarone's procedure isn't monotone
    in alpha, so a case is described by its raw p-value, the smallest p-value its margins
    allow, and the critical value it was compared against at the configured alpha.
    """

    case_id: str
    baseline: CaseSummary
    candidate: CaseSummary
    pass_rate_delta: float  # candidate - baseline
    p_worse: float  # one-sided Fisher exact, uncorrected
    p_worse_min: float  # smallest p_worse these margins allow; 1.0: can never be significant
    p_worse_threshold: float | None  # alpha / K at its step; None: step-down stopped earlier
    p_better: float
    p_better_min: float
    p_better_threshold: float | None
    regressed: bool  # p_worse <= its threshold AND the drop is at least min_drop
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
    alpha: float  # the whole verdict's false-alarm budget, split over the two channels
    alpha_cases: float  # what the per-case family was held at (`CaseComparison` thresholds)
    alpha_suite: float  # what the suite test was compared against
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

    Verdict: `regression` if at least one case is flagged worse by the per-case family, or
    the suite is flagged worse by the suite test. A flagged case is enough on its own: its
    own drop must be at least `min_drop`, but the suite's mean drop needn't be (one broken
    case in 30 moves the mean by only 1/30). Regression wins over any improvement, since
    it's what a CI gate must catch. Otherwise `improvement` if any case or the suite is
    flagged better, else `no_change`.

    The per-case family holds its family-wise false-alarm rate at `alpha_cases` and the
    suite test holds its own at `alpha_suite`. Either one firing is a verdict, so the
    verdict's rate is at most the sum, and the two default to `alpha`/2 (Bonferroni) so that
    sum is `alpha`; the calibration tests and docs/metrics.md measure the actual rates.
    """
    config = config if config is not None else StatisticsConfig()
    suite_alpha = _exact(config.suite_alpha)
    min_drop = _exact(config.min_drop)
    shared = [case_id for case_id in baseline if case_id in candidate]
    cases = compare_cases(baseline, candidate, config)

    suite = None
    if shared:
        deltas = [_rate(candidate[c]) - _rate(baseline[c]) for c in shared]
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
            regressed=test.p_worse <= suite_alpha and -mean_delta >= min_drop,
            improved=test.p_better <= suite_alpha and mean_delta >= min_drop,
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
        alpha_cases=config.cases_alpha,
        alpha_suite=config.suite_alpha,
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


def compare_cases(
    baseline: Mapping[str, CaseSummary],
    candidate: Mapping[str, CaseSummary],
    config: StatisticsConfig | None = None,
) -> list[CaseComparison]:
    """The per-case family on its own: one-sided Fisher exact tests on every shared case,
    Tarone-Holm step-down at `alpha_cases` (worse and better are separate families), then
    the `min_drop` filter. In baseline order.
    """
    config = config if config is not None else StatisticsConfig()
    alpha = _exact(config.cases_alpha)
    min_drop = _exact(config.min_drop)
    shared = [case_id for case_id in baseline if case_id in candidate]
    fisher = [fisher_exact(baseline[c], candidate[c]) for c in shared]
    worse = tarone_holm([f.p_worse for f in fisher], [f.min_p_worse for f in fisher], alpha)
    better = tarone_holm([f.p_better for f in fisher], [f.min_p_better for f in fisher], alpha)

    comparisons = []
    for i, case_id in enumerate(shared):
        before, after = baseline[case_id], candidate[case_id]
        delta = _rate(after) - _rate(before)
        comparisons.append(
            CaseComparison(
                case_id=case_id,
                baseline=before,
                candidate=after,
                pass_rate_delta=float(delta),
                p_worse=float(fisher[i].p_worse),
                p_worse_min=float(fisher[i].min_p_worse),
                p_worse_threshold=_threshold(worse[i]),
                p_better=float(fisher[i].p_better),
                p_better_min=float(fisher[i].min_p_better),
                p_better_threshold=_threshold(better[i]),
                regressed=worse[i].rejected and -delta >= min_drop,
                improved=better[i].rejected and delta >= min_drop,
                score_delta=_difference(before.mean_score, after.mean_score),
                latency_delta_ms=_difference(before.mean_latency_ms, after.mean_latency_ms),
                cost_per_attempt_delta_usd=_difference(
                    _cost_per_attempt(before), _cost_per_attempt(after)
                ),
            )
        )
    return comparisons


def _threshold(decision: StepDownDecision) -> float | None:
    return None if decision.threshold is None else float(decision.threshold)


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
