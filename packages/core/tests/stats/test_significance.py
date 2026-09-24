import itertools
import math
from collections.abc import Sequence
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentprobe_core.stats import CaseSummary, fisher_exact, sign_flip_test, tarone_holm

ALPHA = Fraction(1, 20)


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
    assert fisher_exact(CaseSummary(*baseline), CaseSummary(*candidate)).p_worse == p_worse


def test_fisher_unequal_attempts() -> None:
    # 10/10 vs 0/5: K = 10 passes over 15 attempts, P(X = 0) = comb(5, 5) / comb(15, 5).
    result = fisher_exact(CaseSummary(10, 10), CaseSummary(0, 5))
    assert result.p_worse == Fraction(1, math.comb(15, 5))
    assert result.p_better == 1


@pytest.mark.parametrize(
    ("baseline", "candidate", "min_p_worse", "min_p_better"),
    [
        ((5, 5), (5, 5), 1, 1),  # K = 10: only one table is possible
        ((0, 5), (0, 5), 1, 1),  # K = 0
        ((5, 5), (0, 5), Fraction(1, 252), Fraction(1, 252)),  # K = 5: X in 0..5
        # K = 6: X in 1..5; P(X = 1) = comb(6,1)*comb(4,4)/252, P(X = 5) = comb(6,5)/252.
        ((3, 5), (3, 5), Fraction(6, 252), Fraction(6, 252)),
        # K = 9: X in 4..5; P(X = 4) = comb(9,4)/252 = 1/2.
        ((5, 5), (4, 5), Fraction(1, 2), Fraction(1, 2)),
    ],
)
def test_fisher_minimum_reachable_p(
    baseline: tuple[int, int],
    candidate: tuple[int, int],
    min_p_worse: Fraction,
    min_p_better: Fraction,
) -> None:
    result = fisher_exact(CaseSummary(*baseline), CaseSummary(*candidate))
    assert (result.min_p_worse, result.min_p_better) == (min_p_worse, min_p_better)


@given(summaries(max_attempts=12), summaries(max_attempts=12))
def test_fisher_minimum_is_the_smallest_p_over_tables_with_the_same_margins(
    baseline: CaseSummary, candidate: CaseSummary
) -> None:
    result = fisher_exact(baseline, candidate)
    total = baseline.passes + candidate.passes
    tables = [
        fisher_exact(CaseSummary(total - x, baseline.attempts), CaseSummary(x, candidate.attempts))
        for x in range(candidate.attempts + 1)
        if 0 <= total - x <= baseline.attempts
    ]
    assert result.min_p_worse == min(t.p_worse for t in tables)
    assert result.min_p_better == min(t.p_better for t in tables)


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
    assert fisher_exact(baseline, candidate).p_worse == _brute_force_p_worse(baseline, candidate)


@given(summaries(), summaries())
def test_fisher_properties(baseline: CaseSummary, candidate: CaseSummary) -> None:
    result = fisher_exact(baseline, candidate)
    assert 0 < result.min_p_worse <= result.p_worse <= 1
    assert 0 < result.min_p_better <= result.p_better <= 1
    assert result.p_worse + result.p_better >= 1  # both tails include the observed table
    # Swapping the runs swaps the tails.
    swapped = fisher_exact(candidate, baseline)
    assert (swapped.p_worse, swapped.p_better) == (result.p_better, result.p_worse)
    assert (swapped.min_p_worse, swapped.min_p_better) == (
        result.min_p_better,
        result.min_p_worse,
    )


@given(summaries(), st.integers(1, 20))
def test_fisher_p_worse_grows_with_candidate_passes(baseline: CaseSummary, attempts: int) -> None:
    p = [fisher_exact(baseline, CaseSummary(k, attempts)).p_worse for k in range(attempts + 1)]
    assert p == sorted(p)
    assert p[-1] == 1


# --- Tarone-Holm step-down ---


def _holm_rejections(p_values: Sequence[Fraction], alpha: Fraction) -> list[bool]:
    # Reference Holm, written independently: reject the i-th smallest while p <= alpha/(m-i).
    m = len(p_values)
    rejected = [False] * m
    for rank, index in enumerate(sorted(range(m), key=lambda i: p_values[i])):
        if p_values[index] > alpha / (m - rank):
            break
        rejected[index] = True
    return rejected


def _rejected(p: Sequence[Fraction], min_p: Sequence[Fraction]) -> list[bool]:
    return [d.rejected for d in tarone_holm(p, min_p, ALPHA)]


def test_reduces_to_holm_known_answer_when_every_test_can_reach_significance() -> None:
    raw = [Fraction(x) for x in ("0.01", "0.04", "0.03", "0.005")]
    decisions = tarone_holm(raw, [Fraction(0)] * 4, ALPHA)
    # Holm: 0.005 <= 0.05/4, 0.01 <= 0.05/3, then 0.03 > 0.05/2 stops the step-down.
    assert [d.rejected for d in decisions] == [True, False, False, True]
    assert [d.threshold for d in decisions] == [
        Fraction(1, 60),
        None,  # never reached
        Fraction(1, 40),
        Fraction(1, 80),
    ]
    assert [d.family_size for d in decisions] == [3, None, 2, 4]


def test_unchanged_deterministic_cases_leave_the_family() -> None:
    # One case 5/5 -> 0/5 (p = min p = 1/252) among 29 unchanged 5/5 cases (min p = 1).
    # Holm divides alpha by 30 (1/600 < 1/252: not significant); Tarone's family is K = 1.
    p = [Fraction(1, 252)] + [Fraction(1)] * 29
    min_p = [Fraction(1, 252)] + [Fraction(1)] * 29
    decisions = tarone_holm(p, min_p, ALPHA)
    assert decisions[0] == tarone_holm([p[0]], [min_p[0]], ALPHA)[0]
    assert (decisions[0].rejected, decisions[0].family_size, decisions[0].threshold) == (
        True,
        1,
        ALPHA,
    )
    assert _holm_rejections(p, ALPHA)[0] is False


def test_tarone_step_down_worked_example() -> None:
    # Each case observed at its most extreme table (p = min p): 1/252, 6/252, 6/252, 21/252,
    # 1, 1 (5 runs per case: 5/5->0/5, 4/5->0/5, 5/5->1/5, 3/5->0/5, two unchanged).
    min_p = [Fraction(n, 252) for n in (1, 6, 6, 21)] + [Fraction(1)] * 2
    decisions = tarone_holm(min_p, min_p, ALPHA)
    # Step 1, all six: at K = 1 three can reach 0.05 (3 > 1); at K = 2 the same three reach
    # 0.025 (3 > 2); at K = 3 only 1/252 reaches 1/60 (1 <= 3). 1/252 <= 1/60: reject.
    # Step 2, five left: at K = 1 two reach 0.05 (2 > 1); at K = 2 two reach 0.025. K = 2;
    # 6/252 = 0.0238 <= 0.025: reject.
    # Step 3, four left: only one 6/252 reaches 0.05 at K = 1. 6/252 <= 0.05: reject.
    # Step 4, three left: nothing reaches 0.05, K = 1; 21/252 = 0.083 > 0.05: stop.
    assert [d.family_size for d in decisions] == [3, 2, 1, 1, None, None]
    assert [d.rejected for d in decisions] == [True, True, True, False, False, False]
    # Holm on the same p-values rejects only the first (6/252 > 0.05/5).
    assert _holm_rejections(min_p, ALPHA) == [True, False, False, False, False, False]


def test_tarone_holm_edges() -> None:
    assert tarone_holm([], [], ALPHA) == []
    # Nothing can reach alpha: K = 1, nothing rejected.
    only_untestable = tarone_holm([Fraction(1)], [Fraction(1)], ALPHA)
    assert only_untestable[0].family_size == 1
    assert not only_untestable[0].rejected
    with pytest.raises(ValueError):
        tarone_holm([Fraction(1, 2)], [], ALPHA)


@st.composite
def families(draw: st.DrawFn) -> tuple[list[Fraction], list[Fraction]]:
    # (p, min p) pairs with 0 < min p <= p <= 1, as Fisher produces.
    pairs = draw(st.lists(st.tuples(p_values, p_values), max_size=30))
    min_p = [max(min(a, b), Fraction(1, 10_000)) for a, b in pairs]
    p = [max(a, b, m) for (a, b), m in zip(pairs, min_p, strict=True)]
    return p, min_p


@given(families())
def test_tarone_holm_with_zero_minimums_is_exactly_holm(
    family: tuple[list[Fraction], list[Fraction]],
) -> None:
    p, _ = family
    assert _rejected(p, [Fraction(0)] * len(p)) == _holm_rejections(p, ALPHA)


@given(families())
def test_tarone_holm_properties(family: tuple[list[Fraction], list[Fraction]]) -> None:
    p, min_p = family
    decisions = tarone_holm(p, min_p, ALPHA)
    rejected = [d.rejected for d in decisions]
    # Never less powerful than Holm.
    for tarone, holm in zip(rejected, _holm_rejections(p, ALPHA), strict=True):
        assert tarone or not holm
    for i, d in enumerate(decisions):
        if d.threshold is not None:
            assert d.family_size is not None
            assert d.threshold == ALPHA / d.family_size
            assert 1 <= d.family_size <= len(p)  # never stricter than Bonferroni
        if d.rejected:
            assert d.threshold is not None and p[i] <= d.threshold
            # Rejections are closed downwards in p: anything smaller is rejected too.
            assert all(rejected[j] for j in range(len(p)) if p[j] < p[i])
        if min_p[i] > ALPHA:
            assert not d.rejected  # can never reach significance


@given(st.data())
def test_tarone_holm_rejections_do_not_depend_on_input_order(data: st.DataObject) -> None:
    p, min_p = data.draw(families())
    order = data.draw(st.permutations(range(len(p))))
    shuffled = _rejected([p[i] for i in order], [min_p[i] for i in order])
    assert shuffled == [_rejected(p, min_p)[i] for i in order]


def _binomial(k: int, n: int, p: Fraction) -> Fraction:
    return math.comb(n, k) * p**k * (1 - p) ** (n - k)


def _exact_family_wise_error(true_rates: Sequence[Fraction], attempts: int) -> Fraction:
    """Exact P(the step-down rejects anything) when no case changed: both runs share each
    case's true pass rate. Enumerates every joint outcome, grouping a case's outcomes that
    give the same (p, min p) since the procedure only sees those.
    """
    outcomes = []
    for rate in true_rates:
        grouped: dict[tuple[Fraction, Fraction], Fraction] = {}
        for kb, kc in itertools.product(range(attempts + 1), repeat=2):
            fisher = fisher_exact(CaseSummary(kb, attempts), CaseSummary(kc, attempts))
            key = (fisher.p_worse, fisher.min_p_worse)
            probability = _binomial(kb, attempts, rate) * _binomial(kc, attempts, rate)
            grouped[key] = grouped.get(key, Fraction(0)) + probability
        outcomes.append([(key, prob) for key, prob in grouped.items() if prob])
    false_alarm = Fraction(0)
    for combo in itertools.product(*outcomes):
        if any(_rejected([key[0] for key, _ in combo], [key[1] for key, _ in combo])):
            false_alarm += math.prod((prob for _, prob in combo), start=Fraction(1))
    return false_alarm


@settings(max_examples=40)
@given(
    st.lists(st.fractions(min_value=0, max_value=1, max_denominator=10), min_size=1, max_size=3),
    st.integers(1, 4),
)
def test_tarone_holm_family_wise_error_is_at_most_alpha_exactly(
    true_rates: list[Fraction], attempts: int
) -> None:
    assert _exact_family_wise_error(true_rates, attempts) <= ALPHA


def test_tarone_holm_family_wise_error_exact_at_five_attempts() -> None:
    # The default runs_per_case, with rates where Tarone's family is small and discreteness
    # matters most: one coin-flip case among near-deterministic ones.
    rates = [Fraction(1, 2), Fraction(9, 10), Fraction(19, 20)]
    error = _exact_family_wise_error(rates, 5)
    assert 0 < error <= ALPHA


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
