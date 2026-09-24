"""The tests behind regression detection (ADR 0006, ADR 0014): one-sided Fisher exact tests
per case, Holm's step-down correction, and a paired sign-flip permutation test at suite level.

p-values are exact rationals (`Fraction`), so a p-value that lands exactly on the threshold
(e.g. 1/20 against alpha = 0.05) is compared without floating-point error.
"""

import math
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from agentprobe_core.stats.summary import CaseSummary

# Exact sign-flip enumeration is used while its work stays under this many dictionary updates
# (about a second). 2**21 keeps every test with up to 20 non-zero deltas exact, as ADR 0006
# requires; larger suites stay exact too when the deltas sit on a small lattice (same
# attempts per case in both runs), and fall back to seeded Monte Carlo otherwise.
EXACT_BUDGET = 2**21


def fisher_exact(baseline: CaseSummary, candidate: CaseSummary) -> tuple[Fraction, Fraction]:
    """One-sided Fisher exact p-values `(p_worse, p_better)` for the candidate's pass rate
    being lower / higher than the baseline's.

    Conditional on the total number of passes K over both runs, the candidate's passes X
    follow a hypergeometric distribution under "no change": p_worse = P(X <= observed),
    p_better = P(X >= observed).
    """
    total_passes = baseline.passes + candidate.passes
    total_attempts = baseline.attempts + candidate.attempts
    # weights[x] is proportional to P(X = x); math.comb is 0 outside the support.
    weights = [
        math.comb(total_passes, x)
        * math.comb(total_attempts - total_passes, candidate.attempts - x)
        for x in range(candidate.attempts + 1)
    ]
    denominator = sum(weights)  # = comb(total_attempts, candidate.attempts)
    return (
        Fraction(sum(weights[: candidate.passes + 1]), denominator),
        Fraction(sum(weights[candidate.passes :]), denominator),
    )


def holm(p_values: Sequence[Fraction]) -> list[Fraction]:
    """Holm step-down adjusted p-values, in input order. Rejecting every hypothesis whose
    adjusted p-value is <= alpha controls the family-wise error rate at alpha.
    """
    m = len(p_values)
    adjusted = [Fraction(0)] * m
    running_max = Fraction(0)
    for rank, index in enumerate(sorted(range(m), key=lambda i: p_values[i])):
        running_max = max(running_max, min(Fraction(1), (m - rank) * p_values[index]))
        adjusted[index] = running_max
    return adjusted


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
