# 0014: Statistics implementation

Status: accepted (2026-09-24). Amended the same day: the per-case correction is Tarone–Holm, not plain Holm (user decision, see [Per-case tests](#per-case-tests)).

## Context
[ADR 0006](0006-statistics-methodology.md) picked the methods (approved in PLAN.md §2 #9 / Q5): a case-level bootstrap CI for the suite pass rate, one-sided Fisher exact tests with Holm correction per case, a paired sign-flip permutation test at suite level, and a flag only when a drop is significant at `alpha` and at least `min_drop`. B1.6 implements them in `packages/core/stats`.

This ADR does two things. It records why the case is the unit of resampling. It also records the decisions ADR 0006 left open:
- edge cases: one case, zero variance, small N, different case sets;
- exactness at the thresholds;
- how the per-case and suite tests combine into one verdict;
- the power limits, measured.

The first measurement showed that plain Holm could not flag a single broken case in a realistic suite (see [Power](#power)). The user then chose Tarone's modification for the per-case family. This ADR records that change too.

## Decision

### The case is the unit of resampling
Attempts of one case aren't independent. They share the case's input, the agent's handling of that input, and the judge's rubric.

Given case *i*, the attempts are Bernoulli(p_i), but p_i differs from case to case. The mean of case pass rates therefore has variance

Var(p_i) / C + E[p_i(1 − p_i)] / (C·n)

The first term is the between-case variance; the second is the within-case variance.

Wilson on pooled attempts assumes one common p and C·n independent trials, so it keeps only the second term. A typical suite mixes stable-pass cases, some stable-fail cases and some flaky cases, and in such a suite the first term dominates. The pooled interval is then too narrow by up to a factor of √n: the design effect is 1 + (n − 1)ρ, where ρ is the within-case correlation.

A tested example: 10 stable-pass and 10 stable-fail cases, 5 attempts each.
- Pooled Wilson gives [0.40, 0.60].
- The case-level interval is [0.30, 0.70].

The estimand is the agent's mean pass rate over cases like the suite's. The suite is treated as a sample of the behaviors it covers, which is the usual view for error bars on evals (clustered standard errors). Resampling whole cases with replacement is the cluster bootstrap for that estimand, and it needs no model of the within-case correlation.

Details:
- It is a percentile bootstrap with `bootstrap_resamples` resamples (default 10,000).
- It uses `random.Random(seed)` with a fixed default seed of 0, so the same run always gets the same interval.
- Quantiles are type 7, the same as `statistics.quantiles(method="inclusive")`.

### Binomial floor for zero between-case variance
The bootstrap collapses to a point in two situations: the suite has one case, or every case has the same pass rate (common: all stable-pass). In both, every resample has the same mean, so the interval claims certainty from, for example, 20 cases × 5 runs. The binomial noise within each case is still there; the bootstrap just can't see it.

The fix: report the union of the bootstrap interval and a Wilson interval centred on the suite rate, computed with the effective number of attempts n_eff = C² / Σ(1/n_i). With equal attempts per case, n_eff = C·n.
- The floor only ever widens the interval. When cases differ, the bootstrap interval is the wider one and the floor has no effect.
- A single case gets exactly its own Wilson interval.
- 20 stable-pass cases × 5 attempts give [0.963, 1].

Considered: in the degenerate case, Wilson with cases as the trials (n = C). It is valid, but it creates a discontinuity: 20 stable-pass cases would get a much wider interval than 19 stable-pass cases plus 1 flaky one.

### Measured coverage of the suite CI
Setup:
- Suites were drawn from a known population of case pass rates: 60% at p = 1, 10% at p = 0, 30% spread over 0.3–0.9.
- 5 attempts per case, 1,000 suites per size.

Coverage of the nominal 95% interval:

| Cases | Coverage |
|---|---|
| 10 | 87.3% |
| 30 | 94.1% |
| 100 | 94.3% |

The percentile cluster bootstrap is known to under-cover when there are few clusters. Below about 20 cases, treat the interval as optimistic. A unit test pins coverage at 30 cases to [0.90, 0.99].

### Labels
- `stable-pass` when every attempt passed, `stable-fail` when none did, `flaky` otherwise, as in ADR 0006.
- An error counts as a non-pass. `CaseSummary.errors` is kept separately for display.
- A case with a single attempt can never be `flaky`.
- Labels describe what was observed. They are not tested for significance. For example, 5/5 still has a Wilson lower bound of 0.57.

### Per-case tests
**The Fisher test is one-sided, and always has been.** A regression is a drop, so the "worse" test is p_worse = P(X ≤ observed): X is the candidate's passes under the hypergeometric null, conditional on the table's margins. Improvements use the other tail, p_better = P(X ≥ observed), as a separate family. Neither is ever two-sided.
- Each p-value comes from the hypergeometric pmf using `math.comb` and is kept as an exact `Fraction`.
- The test is valid with different attempt counts in the two runs.
- For reference, a two-sided test would double these p-values here, since the tables are symmetric: 5/5 → 1/5 would go from 6/252 to 12/252, and 3/3 → 0/3 from 1/20 to 1/10, which could then never reach 0.05.

**The correction is Holm's step-down with Tarone's (1990) modification**, applied separately to the "worse" and "better" families.

The problem with plain Holm on Fisher tests: Fisher tests are discrete, and many can never reach significance at all. An unchanged 5/5 → 5/5 case has only one possible table given its margins, so its smallest achievable p is 1. Holm still counts it, dividing `alpha` by every compared case. At 5 runs and 13 or more cases, that made a single broken case (5/5 → 0/5, p = 1/252) impossible to flag.

**Procedure** (`significance.tarone_holm`):
1. For each case, Fisher also returns the smallest p its margins allow (`min_p_worse` / `min_p_better`). That is P(X = the lowest / highest value the margins permit).
2. Tarone's K for a set S of hypotheses is the smallest K ≥ 1 with #{i ∈ S : min_p_i ≤ `alpha`/K} ≤ K. Hypotheses that can't reach `alpha`/K don't count towards the correction.
3. Step-down: sort by p. At each step, compute K over the hypotheses not yet rejected, and reject while p ≤ `alpha`/K. Stop at the first p that isn't.
4. Then the `min_drop` filter applies. That filter only ever removes flags.

**Why it controls the family-wise error rate at `alpha`:**
- Fisher's test is exact conditional on its margins, so condition on every case's margins. The min p values and every K are then fixed.
- For any set I of true null hypotheses, "reject I if min over I of p_i ≤ `alpha`/K(I)" is a level-`alpha` test. Only the hypotheses in R_I (those with min p ≤ `alpha`/K(I)) can reject, there are at most K(I) of them, and each rejects with probability at most `alpha`/K(I). By the union bound the total is at most `alpha`.
- K is monotone: if I ⊆ J then K(I) ≤ K(J), since fewer hypotheses can only lower the count. So the step-down is a shortcut of closed testing with those local tests. For any I that contains a rejected hypothesis, I's smallest-p member was rejected at an earlier or equal step, against a threshold no larger than `alpha`/K(I).
- This holds for every set of margins, so it holds unconditionally.

This is the step-down form described by Hommel & Krummenauer (1998, *Biometrics* 54:673–681).

**Properties, each tested:**
- With every min p at 0 it is exactly Holm, checked against an independent Holm implementation.
- It never rejects less than Holm, because K ≤ the number of remaining hypotheses.
- The set of rejected cases doesn't depend on input order.
- A hypothesis whose min p exceeds `alpha` is never rejected.

**No adjusted p-values.** Tarone's procedure isn't monotone in `alpha`: raising `alpha` can let more tests reach `alpha`/K, raise K, and lower the threshold. So "the smallest `alpha` at which this case is rejected" isn't well defined. `CaseComparison` therefore reports each case's raw `p_worse`, its `p_worse_min`, and `p_worse_threshold`. The threshold is the `alpha`/K it was compared against, or `None` when the step-down stopped before reaching it. The previous `p_worse_adjusted` / `p_better_adjusted` fields are gone.

**Performance.** Fisher results are memoized per table (`lru_cache`, 4,096 entries), since a suite has few distinct tables: 36 at 5 runs. Identical tables then share one `Fraction`, which keeps the step-down's exact sorting fast. The sort key (float, Fraction) gives the exact order because rounding to float is monotone.

### Suite test
- **What is tested.** A paired sign-flip test on per-case pass-rate deltas, over the cases both runs share. The statistic is the sum of the deltas.
- **Zero deltas are dropped**, since they add 0 under either sign. The p-value is unchanged, so ADR 0006's "exact up to 20 cases" rule is applied to non-zero deltas.
- **How the exact null is computed.** Deltas are scaled to integers by the LCM of their denominators. Dynamic programming then counts how many sign assignments reach each possible sum, instead of enumerating all 2^C assignments. Integer sums keep ties with the observed statistic exact.
- **When it is exact.** Whenever the work stays under 2^21 dictionary updates (about a second). That covers:
  - every test with 20 or fewer non-zero deltas, as ADR 0006 requires;
  - much larger suites when `runs_per_case` is the same in both runs, because the sums then sit on a lattice of 1/n steps (a 200-case suite is exact in the tests).
- **Otherwise: seeded Monte Carlo** with `permutation_draws` draws. The p-value is (1 + hits) / (1 + draws), so it is never 0 (Phipson & Smyth 2010).
- **Assumption.** With no change, each delta is symmetric about 0. This holds exactly when a case has the same number of attempts in both runs. With different attempt counts it is only approximate: the mean is still 0, but the distribution isn't exactly symmetric.
- **One changed case** gives p ≥ 1/2. The suite test needs several cases moving in the same direction.

### Thresholds are compared exactly
- p-values are `Fraction`s.
- `alpha` and `min_drop` are converted from their decimal `repr` (0.05 → 1/20), so a p-value equal to `alpha`, or a drop equal to `min_drop`, meets the bar.
- Floats get both wrong in real cases:
  - 3/3 → 0/3 has p = 1/20 exactly;
  - 5 of 20 cases each dropping by 0.2 is a drop of exactly 0.05, which floats compute as 0.0499….

### Verdict
**Rule.**
- `regression` if at least one case is flagged worse, or the suite is. A case is flagged when the Tarone–Holm step-down rejects it at `alpha` AND its own pass rate dropped by at least `min_drop`.
- **A flagged case is enough on its own**, even when the suite's mean drop is below `min_drop` and the suite test isn't significant. One broken case in 30 moves the suite mean by only 1/30 = 0.033.
- The demo scenario is a test (`test_demo_one_refund_case_breaking_in_30_is_a_regression`), with and without flaky cases around it: support-bot v2's refund case goes 5/5 → 0/5 in a 30-case suite. The verdict is `regression`, the refund case is compared against `alpha` itself (K = 1), the suite drop is under `min_drop`, and the suite test isn't significant.
- Otherwise `improvement` if any case or the suite is flagged better, by the mirror rule.
- Otherwise `no_change`.
- A regression wins over an improvement, because a regression is what a CI gate has to catch.

**Error rate: what is proven, and what isn't.**
- **The per-case family's false-alarm rate is at most `alpha`.** This follows from the argument above, and is checked two ways:
  - *Exactly*, by enumerating every joint outcome for small families (up to 3 cases at up to 4 runs from Hypothesis-drawn true rates, plus 3 cases at 5 runs). For example, true rates 1/2, 9/10 and 19/20 at 5 runs give exactly 1.10%.
  - *By seeded simulation* (`test_family_wise_error.py`, 1,000 trials per cell): suite sizes 5, 13, 30 and 100 × 20% / 50% / 100% flaky, every case at a different true rate (0.05–0.95), and every case a coin flip, plus 3 and 10 runs per case. The test requires the upper 97.5% Wilson bound of each measured rate to be at or below `alpha`, so passing isn't luck of the seed. The highest measured rate is 3.2%, with an upper bound of 4.5%.
- **The whole verdict is not held at `alpha`.** It adds the suite test, which is also held at `alpha`, so its worst case is 2·`alpha` (union bound).
  - In the realistic reference scenario it stays low: 2.3%.
  - On heavily flaky suites it exceeds `alpha`. [docs/metrics.md](../metrics.md) measures up to 6.5% (100 cases each at its own true rate) and 6.2% (30 or 100 cases, all flaky or all coin flips).
  - The calibration unit test pins it at ≤ 2·`alpha`.
  - Holding the verdict itself at `alpha` would mean splitting `alpha` between the family and the suite test (for example `alpha`/2 each). That changes the approved method, so it is left for a decision.
  - The cost of a split, worked out analytically: at 5 runs a single break (p = 1/252) would still be flagged, but at 3 runs (p = 1/20) it never could be.

**Label-transition lists** (`newly_failing`, `newly_passing`, `newly_flaky`, `no_longer_flaky`) are descriptive and can overlap. For example, flaky → stable-fail appears in both `newly_failing` and `no_longer_flaky`.

**Different case sets.** Only shared cases are compared, and the report lists `added` and `removed`, so adding a hard case never looks like a regression. With no shared cases, `suite` is `None` and the verdict is `no_change`.

**Metric deltas.** Each is taken over the shared cases where both runs report the metric:
- score: the mean of the per-case mean scores;
- latency: the mean of the per-case mean latencies;
- cost: per attempt, summed over cases. This is the cost of one pass through the suite, so runs with different `runs_per_case` compare fairly.

### CLI flags
`StatisticsConfig.override(**flags)` applies CLI flags on top of the YAML `statistics:` block. It skips flags that weren't given and validates the rest the same way the YAML is validated. The Typer options that call it arrive with `agentprobe run` (D1.1) and `agentprobe compare` (D2.1).

### Power
**Why plain Holm was replaced.** At n runs per case, the smallest possible one-sided Fisher p is 1 / C(2n, n). Holm's first step multiplies it by m, the number of compared cases, so under Holm a single case could be flagged only when m ≤ `alpha`·C(2n, n):

| Runs per case | Smallest p | Largest m with a possible per-case flag under Holm |
|---|---|---|
| 3 | 1/20 | 1 |
| 5 | 1/252 | 12 |
| 6 | 1/924 | 46 |
| 8 | 1/12,870 | 643 |
| 10 | 1/184,756 | 9,237 |

At 5 runs and 30 cases, Holm never flagged a deterministic break of one case (5/5 → 0/5). The suite test couldn't catch it either, because one changed case gives a sign-flip p of 1/2. Measured detection was 4.1%.

**With Tarone–Holm.** Unchanged deterministic cases (min p = 1) leave the family, so a single break is flagged at any suite size. A test covers 5 to 500 cases at 3, 5 and 10 runs. Measured in [docs/metrics.md](../metrics.md), reference scenario:

| | Holm | Tarone–Holm |
|---|---|---|
| One broken case detected | 4.1% | 100% |
| Three cases turning flaky detected | 20.2% | 38.5% |
| False alarms | 0.7% | 2.3% |

**Remaining limits, documented and tested:**
- **At 3 runs per case**, a break has p = 1/20, exactly `alpha`. Any other case whose margins can reach `alpha` pushes K to 2 or more, so detection is 38.4% in the reference mix of flaky cases. Use 5 or more runs.
- **A case that only turns flaky** (5/5 → 3/5, p = 56/252) is weak evidence at 5 runs whatever the correction. More runs per case, or several cases moving together, are what catch it.
- **1 or 2 attempts per case** can never flag a case. The smallest p values there are 1/2 and 1/6.

## Consequences
- The executor (B1.7) builds one `CaseSummary` per case. `run_case_summaries` maps onto it column for column: `passes`, `attempts`, `pass_rate`, `label`, `mean_score`, `mean_latency_ms` and `total_cost` (as `cost_usd`).
- All outputs are frozen dataclasses. `dataclasses.asdict` makes them JSON-ready for the compare endpoint (B2.5) and the CLI.
- `compare_cases()` runs the per-case family on its own. `compare_runs()` uses it, and the family-wise error test calls it directly.
- `test_family_wise_error.py` adds about 12 s to `pnpm check`. That is the price of a seeded proof across 24 scenarios, which the user asked to be a test rather than only a script.
- Hypothesis (`hypothesis==6.168.1`) is a workspace dev dependency. `packages/core/tests/stats/conftest.py` loads a derandomized profile with no example database and no deadline, so the property tests are deterministic.
- `scripts/measure_false_alarms.py` and [docs/metrics.md](../metrics.md) measure the false-alarm rate and the detection power. They are the source for the SPEC.md §15 metric.
