"""The tests behind regression detection (ADR 0006, ADR 0014): one-sided Fisher exact tests
per case, Holm's step-down correction with Tarone's modification for discrete tests, and a
paired sign-flip permutation test at suite level.

p-values are exact rationals (`Fraction`), so a p-value that lands exactly on the threshold
(e.g. 1/20 against alpha = 0.05) is compared without floating-point error.
"""

import math
import random
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from agentprobe_core.stats.summary import CaseSummary

# Exact sign-flip enumeration is used while its work stays under this many dictionary updates
# (about a second). 2**21 keeps every test with up to 20 non-zero deltas exact, as ADR 0006
# requires; larger suites stay exact too when the deltas sit on a small lattice (same
# attempts per case in both runs), and fall back to seeded Monte Carlo otherwise.
EXACT_BUDGET = 2**21


@dataclass(frozen=True)
class FisherResult:
    """One-sided Fisher exact p-values for the candidate's pass rate being lower (`p_worse`)
    or higher (`p_better`) than the baseline's, and the smallest p-value each direction could
    reach given the table's margins (what Tarone's correction needs).
    """

    p_worse: Fraction
    p_better: Fraction
    min_p_worse: Fraction
    min_p_better: Fraction


def fisher_exact(baseline: CaseSummary, candidate: CaseSummary) -> FisherResult:
    """Conditional on the total number of passes K over both runs, the candidate's passes X
    follow a hypergeometric distribution under "no change": p_worse = P(X <= observed),
    p_better = P(X >= observed). Both tests are one-sided.

    The margins (attempts per run and K) fix the support of X, so the smallest reachable
    p_worse is P(X = lowest possible x). When K = 0 or K = all attempts (e.g. 5/5 vs 5/5)
    only one table is possible and that minimum is 1: no outcome could ever be significant.
    """
    return _fisher(baseline.passes, baseline.attempts, candidate.passes, candidate.attempts)


# A suite has few distinct tables (36 at 5 runs per case), and sharing one result per table
# also makes the step-down's sorting cheap: equal p-values are then the same object.
@lru_cache(maxsize=4096)
def _fisher(
    baseline_passes: int, baseline_attempts: int, candidate_passes: int, candidate_attempts: int
) -> FisherResult:
    total_passes = baseline_passes + candidate_passes
    total_attempts = baseline_attempts + candidate_attempts
    # weights[x] is proportional to P(X = x); math.comb is 0 outside the support.
    weights = [
        math.comb(total_passes, x)
        * math.comb(total_attempts - total_passes, candidate_attempts - x)
        for x in range(candidate_attempts + 1)
    ]
    denominator = sum(weights)  # = comb(total_attempts, candidate_attempts)
    support = [weight for weight in weights if weight]
    return FisherResult(
        p_worse=Fraction(sum(weights[: candidate_passes + 1]), denominator),
        p_better=Fraction(sum(weights[candidate_passes:]), denominator),
        min_p_worse=Fraction(support[0], denominator),
        min_p_better=Fraction(support[-1], denominator),
    )


@dataclass(frozen=True)
class StepDownDecision:
    rejected: bool
    # alpha / K at this hypothesis's step. None: the step-down stopped before reaching it.
    threshold: Fraction | None
    family_size: int | None  # K: Tarone's family size at that step


def tarone_holm(
    p_values: Sequence[Fraction], min_p_values: Sequence[Fraction], alpha: Fraction
) -> list[StepDownDecision]:
    """Holm's step-down procedure with Tarone's (1990) modification at every step. Controls
    the family-wise error rate at `alpha` for discrete tests (ADR 0014 has the argument).

    Tarone: a hypothesis whose smallest reachable p-value is above alpha / K can never be
    rejected at that level, so it needn't count towards the correction. K is the smallest
    K >= 1 such that at most K hypotheses can reach alpha / K. Step-down: go through the
    p-values from smallest to largest; at each step recompute K over the hypotheses not yet
    rejected and reject while p <= alpha / K; stop at the first p that isn't.

    With every min_p_value at 0 this is exactly Holm. K never exceeds the number of
    remaining hypotheses, so it rejects everything Holm rejects, and more when some tests
    can't reach significance (e.g. unchanged 5/5 -> 5/5 cases, whose minimum p is 1).
    Decisions are in input order; ties in p keep input order.
    """
    if len(min_p_values) != len(p_values):
        raise ValueError("need one minimum p-value per p-value")
    order = sorted(range(len(p_values)), key=lambda i: _sort_key(p_values[i]))
    decisions = [StepDownDecision(rejected=False, threshold=None, family_size=None)] * len(p_values)
    # Min p-values of the hypotheses not yet rejected.
    remaining = sorted(min_p_values, key=_sort_key)
    for index in order:
        family_size = _tarone_family_size(remaining, alpha)
        threshold = alpha / family_size
        rejected = p_values[index] <= threshold
        decisions[index] = StepDownDecision(rejected, threshold, family_size)
        if not rejected:
            break
        del remaining[bisect_left(remaining, min_p_values[index])]
    return decisions


def _sort_key(value: Fraction) -> tuple[float, Fraction]:
    # The exact order, fast: rounding to float is monotone, so floats only tie when the
    # values are equal or too close for a double, and the Fraction then decides.
    return float(value), value


def _tarone_family_size(sorted_min_p_values: Sequence[Fraction], alpha: Fraction) -> int:
    """The smallest K >= 1 with #{min p <= alpha / K} <= K. That count only falls as K grows,
    so binary search; K = len(values) always qualifies.
    """
    low, high = 1, max(1, len(sorted_min_p_values))
    while low < high:
        middle = (low + high) // 2
        if bisect_right(sorted_min_p_values, alpha / middle) <= middle:
            high = middle
        else:
            low = middle + 1
    return low


@dataclass(frozen=True)
class SignFlipResult:
    p_worse: Fraction  # P(T <= observed): evidence the deltas are negative
    p_better: Fraction  # P(T >= observed)
    exact: bool  # False: seeded Monte Carlo estimate


def sign_flip_test(
    deltas: Sequence[Fraction],
    *,
    draws: int,
    seed: int,
    exact_budget: int = EXACT_BUDGET,
) -> SignFlipResult:
    """Paired sign-flip permutation test on per-case deltas (candidate - baseline).

    Under "no change" each case's two runs are exchangeable, so each delta is as likely to
    have either sign. The statistic is the sum of deltas; its null distribution comes from
    every sign assignment. Zero deltas are dropped: they add 0 under either sign.
    """
    nonzero = [delta for delta in deltas if delta]
    # Integers make every sum exact, so ties with the observed statistic count correctly.
    scale = math.lcm(*(delta.denominator for delta in nonzero))
    values = [int(delta * scale) for delta in nonzero]
    observed = sum(values)
    if _enumeration_cost(values) <= exact_budget:
        return _exact_sign_flip(values, observed)
    return _monte_carlo_sign_flip(values, observed, draws, seed)


def _enumeration_cost(values: Sequence[int]) -> int:
    # After i values there are at most min(2**i, 2 * sum|v| + 1) distinct sums.
    cost = reach = 0
    for count, value in enumerate(values, start=1):
        reach += abs(value)
        cost += min(2**count, 2 * reach + 1)
    return cost


def _exact_sign_flip(values: Sequence[int], observed: int) -> SignFlipResult:
    # Distribution of the signed sum over all 2**len(values) sign assignments.
    counts: dict[int, int] = {0: 1}
    for value in values:
        step: defaultdict[int, int] = defaultdict(int)
        for total, count in counts.items():
            step[total + value] += count
            step[total - value] += count
        counts = step
    assignments = 2 ** len(values)
    return SignFlipResult(
        p_worse=Fraction(sum(c for t, c in counts.items() if t <= observed), assignments),
        p_better=Fraction(sum(c for t, c in counts.items() if t >= observed), assignments),
        exact=True,
    )


def _monte_carlo_sign_flip(
    values: Sequence[int], observed: int, draws: int, seed: int
) -> SignFlipResult:
    if draws < 1:
        raise ValueError(f"draws must be at least 1, got {draws}")
    rng = random.Random(seed)  # noqa: S311 (seeded resampling, not crypto)
    worse = better = 0
    for _ in range(draws):
        signs = rng.getrandbits(len(values))
        total = sum(v if signs >> i & 1 else -v for i, v in enumerate(values))
        worse += total <= observed
        better += total >= observed
    # Counting the observed assignment as one of the draws keeps the estimate a valid p-value
    # that is never 0 (Phipson & Smyth 2010).
    return SignFlipResult(
        p_worse=Fraction(1 + worse, 1 + draws),
        p_better=Fraction(1 + better, 1 + draws),
        exact=False,
    )
