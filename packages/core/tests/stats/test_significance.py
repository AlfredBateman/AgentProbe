import itertools
import math
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agentprobe_core.stats import CaseSummary, fisher_exact, holm, sign_flip_test


@st.composite
def summaries(draw: st.DrawFn, max_attempts: int = 20) -> CaseSummary:
    attempts = draw(st.integers(1, max_attempts))
    return CaseSummary(passes=draw(st.integers(0, attempts)), attempts=attempts)


fractions = st.fractions(min_value=-1, max_value=1, max_denominator=20)
p_values = st.fractions(min_value=0, max_value=1, max_denominator=1000)

# --- Fisher exact ---


@pytest.mark.parametrize(
    ("baseline", "candidate", "p_worse"),
    [
        # Fisher's lady tasting tea: 3 of 4 cups right vs 1 of 4, one-sided p = 17/70.
        ((3, 4), (1, 4), Fraction(17, 70)),
        # ADR 0006's small-N examples at 5 runs per case: 5/5 -> 1/5 is significant, 5/5 ->
        # 2/5 is not.
        ((5, 5), (1, 5), Fraction(6, 252)),
        ((5, 5), (2, 5), Fraction(21, 252)),
        ((5, 5), (0, 5), Fraction(1, 252)),  # 1 / comb(10, 5): the smallest p at 5 runs
        ((3, 3), (0, 3), Fraction(1, 20)),  # lands exactly on alpha = 0.05
        ((5, 5), (5, 5), Fraction(1)),
        ((0, 5), (0, 5), Fraction(1)),
        ((1, 1), (0, 1), Fraction(1, 2)),  # one attempt each can never be significant
    ],
)
def test_fisher_known_answers(
    baseline: tuple[int, int], candidate: tuple[int, int], p_worse: Fraction
) -> None:
    assert fisher_exact(CaseSummary(*baseline), CaseSummary(*candidate))[0] == p_worse


def test_fisher_unequal_attempts() -> None:
    # 10/10 vs 0/5: K = 10 passes over 15 attempts, P(X = 0) = comb(5, 5) / comb(15, 5).
    p_worse, p_better = fisher_exact(CaseSummary(10, 10), CaseSummary(0, 5))
    assert p_worse == Fraction(1, math.comb(15, 5))
    assert p_better == 1


def _brute_force_p_worse(baseline: CaseSummary, candidate: CaseSummary) -> Fraction:
    # Label every attempt, then count the ways to deal `candidate.attempts` of them to the
    # candidate that give it at most its observed passes.
    outcomes = [True] * (baseline.passes + candidate.passes) + [False] * (
        baseline.attempts + candidate.attempts - baseline.passes - candidate.passes
    )
    deals = list(itertools.combinations(range(len(outcomes)), candidate.attempts))
    extreme = sum(sum(outcomes[i] for i in deal) <= candidate.passes for deal in deals)
    return Fraction(extreme, len(deals))


@given(summaries(max_attempts=6), summaries(max_attempts=6))
def test_fisher_matches_brute_force_enumeration(
    baseline: CaseSummary, candidate: CaseSummary
) -> None:
    assert fisher_exact(baseline, candidate)[0] == _brute_force_p_worse(baseline, candidate)


@given(summaries(), summaries())
def test_fisher_properties(baseline: CaseSummary, candidate: CaseSummary) -> None:
    p_worse, p_better = fisher_exact(baseline, candidate)
    assert 0 < p_worse <= 1
    assert 0 < p_better <= 1
    assert p_worse + p_better >= 1  # both tails include the observed table
    # Swapping the runs swaps the tails.
    assert fisher_exact(candidate, baseline) == (p_better, p_worse)


@given(summaries(), st.integers(1, 20))
def test_fisher_p_worse_grows_with_candidate_passes(baseline: CaseSummary, attempts: int) -> None:
    p = [fisher_exact(baseline, CaseSummary(k, attempts))[0] for k in range(attempts + 1)]
    assert p == sorted(p)
    assert p[-1] == 1


# --- Holm ---


def test_holm_known_answer() -> None:
    raw = [Fraction(x) for x in ("0.01", "0.04", "0.03", "0.005")]
    # Sorted: 0.005*4 = 0.02, 0.01*3 = 0.03, 0.03*2 = 0.06, max(0.06, 0.04*1) = 0.06.
    assert holm(raw) == [Fraction(x) for x in ("0.03", "0.06", "0.06", "0.02")]


def test_holm_caps_at_one_and_handles_edges() -> None:
    assert holm([Fraction(1, 2), Fraction(3, 4)]) == [Fraction(1), Fraction(1)]
    assert holm([Fraction(1, 3)]) == [Fraction(1, 3)]
    assert holm([]) == []


@given(st.lists(p_values, max_size=30))
def test_holm_properties(raw: list[Fraction]) -> None:
    adjusted = holm(raw)
    m = len(raw)
    for p, q in zip(raw, adjusted, strict=True):
        assert p <= q <= min(Fraction(1), m * p)  # at least raw, at most Bonferroni
    # Preserves the order of the raw p-values.
    for i, j in itertools.combinations(range(m), 2):
        if raw[i] < raw[j]:
            assert adjusted[i] <= adjusted[j]


@given(st.data())
def test_holm_is_permutation_equivariant(data: st.DataObject) -> None:
    raw = data.draw(st.lists(p_values, max_size=30))
    order = data.draw(st.permutations(range(len(raw))))
    shuffled = holm([raw[i] for i in order])
    assert shuffled == [holm(raw)[i] for i in order]


# --- Sign-flip permutation test ---


def _brute_force_sign_flip(deltas: list[Fraction]) -> tuple[Fraction, Fraction]:
    observed = sum(deltas, Fraction(0))
    sums = [
        sum((s * d for s, d in zip(signs, deltas, strict=True)), Fraction(0))
        for signs in itertools.product((1, -1), repeat=len(deltas))
    ]
    return (
        Fraction(sum(t <= observed for t in sums), len(sums)),
        Fraction(sum(t >= observed for t in sums), len(sums)),
    )


@given(st.lists(fractions, max_size=10))
def test_sign_flip_exact_matches_brute_force(deltas: list[Fraction]) -> None:
    result = sign_flip_test(deltas, draws=100, seed=0)
    assert result.exact
    assert (result.p_worse, result.p_better) == _brute_force_sign_flip(deltas)


def test_sign_flip_known_answers() -> None:
    six_drops = sign_flip_test([Fraction(-1, 5)] * 6, draws=100, seed=0)
    assert (six_drops.p_worse, six_drops.p_better) == (Fraction(1, 64), Fraction(1))
    # One changed case can never be significant at suite level: p = 1/2.
    assert sign_flip_test([Fraction(-1)], draws=100, seed=0).p_worse == Fraction(1, 2)


def test_sign_flip_zero_deltas_mean_no_evidence() -> None:
    result = sign_flip_test([Fraction(0)] * 30, draws=100, seed=0)
    assert (result.p_worse, result.p_better, result.exact) == (1, 1, True)
    assert sign_flip_test([], draws=100, seed=0).p_worse == 1


def test_sign_flip_ignores_zero_deltas() -> None:
    changed = [Fraction(-1, 5), Fraction(-2, 5), Fraction(1, 5)]
    padded = changed + [Fraction(0)] * 100
    assert sign_flip_test(padded, draws=100, seed=0) == sign_flip_test(changed, draws=100, seed=0)


def test_sign_flip_stays_exact_for_large_suites_on_a_small_lattice() -> None:
    # 200 changed cases, all at 5 runs per case: sums live on a lattice of 1/5 steps.
    deltas = [Fraction(-1, 5)] * 120 + [Fraction(1, 5)] * 80
    assert sign_flip_test(deltas, draws=100, seed=0).exact


def test_sign_flip_up_to_20_nonzero_deltas_is_always_exact() -> None:
    # Pairwise-incommensurable deltas: every sign assignment gives a distinct sum.
    twenty = [Fraction(1, 2**i) for i in range(1, 21)]
    assert sign_flip_test(twenty, draws=100, seed=0).exact


def test_sign_flip_monte_carlo_agrees_with_exact() -> None:
    deltas = [Fraction(k, 5) for k in (-1, -1, -2, -1, 1, -3, -1, 2, -1, -1, 1, -2)]
    exact = sign_flip_test(deltas, draws=100, seed=0)
    estimate = sign_flip_test(deltas, draws=20_000, seed=3, exact_budget=0)
    assert exact.exact and not estimate.exact
    assert float(estimate.p_worse) == pytest.approx(float(exact.p_worse), abs=0.01)
    assert float(estimate.p_better) == pytest.approx(float(exact.p_better), abs=0.01)
    # Seeded: the same draws every time.
    assert sign_flip_test(deltas, draws=500, seed=3, exact_budget=0) == sign_flip_test(
        deltas, draws=500, seed=3, exact_budget=0
    )


def test_sign_flip_monte_carlo_p_value_is_never_zero() -> None:
    result = sign_flip_test([Fraction(-1)] * 40, draws=999, seed=0, exact_budget=0)
    assert result.p_worse == Fraction(1, 1000)  # (1 + 0) / (1 + draws)


def test_sign_flip_monte_carlo_rejects_zero_draws() -> None:
    with pytest.raises(ValueError):
        sign_flip_test([Fraction(-1)], draws=0, seed=0, exact_budget=0)
