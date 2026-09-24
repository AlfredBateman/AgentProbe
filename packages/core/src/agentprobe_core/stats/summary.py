"""Per-case pass rates, labels and Wilson intervals, and the suite pass rate with its
case-level bootstrap confidence interval (SPEC.md §4.6, ADR 0006, ADR 0014).
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist, fmean
from typing import Literal

Label = Literal["stable-pass", "stable-fail", "flaky"]

DEFAULT_SEED = 0
DEFAULT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float


@dataclass(frozen=True)
class CaseSummary:
    """One case's attempts in one run.

    `passes` counts attempts where every expectation passed. `errors` (timeouts or adapter
    failures that survived retries) are a subset of the non-passes, kept separate so a report
    can tell "the agent broke" from "the agent was judged wrong". `cost_usd` is the total over
    the attempts; `mean_score` and `mean_latency_ms` are means over them. None: not reported.
    """

    passes: int
    attempts: int
    errors: int = 0
    mean_score: float | None = None
    mean_latency_ms: float | None = None
    cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError(f"attempts must be at least 1, got {self.attempts}")
        if not 0 <= self.passes <= self.attempts:
            raise ValueError(f"passes must be in 0..{self.attempts}, got {self.passes}")
        if not 0 <= self.errors <= self.attempts - self.passes:
            raise ValueError(
                f"errors must be in 0..{self.attempts - self.passes} (a subset of the "
                f"non-passing attempts), got {self.errors}"
            )

    @property
    def pass_rate(self) -> float:
        return self.passes / self.attempts

    @property
    def label(self) -> Label:
        """`stable-pass` when every attempt passed, `stable-fail` when none did, `flaky`
        otherwise. An error counts as a non-pass. The label describes what was observed, not
        a claim about the agent: with one attempt a case is never `flaky`, and a `stable-pass`
        over 5 attempts is still compatible with a true pass rate of ~57% (its Wilson lower
        bound).
        """
        if self.passes == self.attempts:
            return "stable-pass"
        if self.passes == 0:
            return "stable-fail"
        return "flaky"

    def wilson(self, confidence: float = DEFAULT_CONFIDENCE) -> Interval:
        return wilson_interval(self.passes, self.attempts, confidence)


def wilson_interval(passes: int, attempts: int, confidence: float = DEFAULT_CONFIDENCE) -> Interval:
    """Wilson score interval for a binomial proportion. Unlike the normal (Wald) interval it
    stays inside [0, 1] and doesn't collapse to a point at 0/n or n/n.
    """
    if attempts < 1 or not 0 <= passes <= attempts:
        raise ValueError(f"need 0 <= passes <= attempts and attempts >= 1: {passes}/{attempts}")
    return _wilson(passes / attempts, attempts, confidence)


def _wilson(p: float, n: float, confidence: float) -> Interval:
    """Wilson interval around proportion `p` observed over `n` trials. `n` may be fractional
    (an effective sample size).
    """
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    z2 = z * z
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half_width = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    # The interval always contains p, with lower = 0 exactly at p = 0 and upper = 1 at p = 1;
    # clamping keeps floating-point error from breaking either property.
    return Interval(
        lower=min(p, max(0.0, center - half_width)),
        upper=max(p, min(1.0, center + half_width)),
    )


@dataclass(frozen=True)
class SuiteStats:
    pass_rate: float  # the mean of per-case pass rates, not pooled attempts
    ci: Interval
    confidence: float
    cases: int
    attempts: int


def suite_stats(
    cases: Sequence[CaseSummary],
    *,
    resamples: int = 10_000,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = DEFAULT_SEED,
) -> SuiteStats:
    """The suite pass rate (mean of per-case pass rates) and its confidence interval.

    The interval is a percentile bootstrap that resamples whole cases, never single
    attempts: attempts of one case share that case's difficulty, so they're correlated, and
    treating them as independent (e.g. Wilson on pooled attempts) would be too narrow.

    The bootstrap only sees spread *between* cases. When there is none (one case, or every
    case at the same rate, e.g. all stable-pass) it collapses to a point, although each
    case's attempts still carry binomial noise. So the interval is widened, never narrowed,
    to cover the Wilson interval at the suite rate with the attempts' effective sample size
    (ADR 0014). With one case that is exactly that case's Wilson interval.
    """
    if not cases:
        raise ValueError("a suite needs at least one case")
    if resamples < 1:
        raise ValueError(f"resamples must be at least 1, got {resamples}")
    rates = [case.pass_rate for case in cases]
    point = fmean(rates)
    rng = random.Random(seed)  # noqa: S311 (seeded resampling, not crypto)
    means = sorted(fmean(rng.choices(rates, k=len(rates))) for _ in range(resamples))
    tail = (1 - confidence) / 2
    boot = Interval(_quantile(means, tail), _quantile(means, 1 - tail))
    # Variance of a mean of case rates that all equal p: p(1-p)/C^2 * sum(1/n_i).
    effective_n = len(cases) ** 2 / math.fsum(1 / case.attempts for case in cases)
    floor = _wilson(point, effective_n, confidence)
    return SuiteStats(
        pass_rate=point,
        ci=Interval(min(boot.lower, floor.lower), max(boot.upper, floor.upper)),
        confidence=confidence,
        cases=len(cases),
        attempts=sum(case.attempts for case in cases),
    )


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (Hyndman-Fan type 7, `statistics.quantiles`'
    "inclusive" method) at any q in [0, 1].
    """
    position = (len(sorted_values) - 1) * q
    below = math.floor(position)
    above = min(below + 1, len(sorted_values) - 1)
    fraction = position - below
    return sorted_values[below] + fraction * (sorted_values[above] - sorted_values[below])
