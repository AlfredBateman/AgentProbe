# 0014: Statistics implementation

Status: accepted (2026-09-24)

## Context
[ADR 0006](0006-statistics-methodology.md) picked the methods (approved in PLAN.md §2 #9 / Q5): a case-level bootstrap CI for the suite pass rate, one-sided Fisher exact tests with Holm correction per case, a paired sign-flip permutation test at suite level, and a flag only when a drop is significant at `alpha` and at least `min_drop`. B1.6 implements them in `packages/core/stats`.

This ADR does two things. It records why the case is the unit of resampling. It also records the decisions ADR 0006 left open:
- edge cases: one case, zero variance, small N, different case sets;
- exactness at the thresholds;
- how the per-case and suite tests combine into one verdict;
- the power limits, measured.

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
- One-sided Fisher exact p-values are computed in both directions (`p_worse`, `p_better`). Each comes from the hypergeometric pmf using `math.comb` and is kept as an exact `Fraction`. The test is valid with different attempt counts in the two runs.
- Holm is applied separately to the "worse" family and the "better" family. Each family holds its family-wise error rate at `alpha`.

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
- `regression` if any case is flagged worse (Holm-adjusted `p_worse` ≤ `alpha` and a drop of at least `min_drop`) or the suite is.
- Otherwise `improvement` if any case or the suite is flagged better, by the mirror rule.
- Otherwise `no_change`.
- A regression wins over an improvement, because a regression is what a CI gate has to catch.

**Error rate.** The per-case family and the suite test are each held at `alpha`, so the verdict's worst-case false-alarm rate is 2·`alpha` (union bound). `alpha` is not split in half, for two reasons:
- ADR 0006 sets `alpha` per test.
- The measured rate is far below `alpha` (0.7% in the reference scenario of [docs/metrics.md](../metrics.md); at most 2.8% across the sensitivity scenarios).

A calibration unit test pins the rate at ≤ 2·`alpha`.

**Label-transition lists** (`newly_failing`, `newly_passing`, `newly_flaky`, `no_longer_flaky`) are descriptive and can overlap. For example, flaky → stable-fail appears in both `newly_failing` and `no_longer_flaky`.

**Different case sets.** Only shared cases are compared, and the report lists `added` and `removed`, so adding a hard case never looks like a regression. With no shared cases, `suite` is `None` and the verdict is `no_change`.

**Metric deltas.** Each is taken over the shared cases where both runs report the metric:
- score: the mean of the per-case mean scores;
- latency: the mean of the per-case mean latencies;
- cost: per attempt, summed over cases. This is the cost of one pass through the suite, so runs with different `runs_per_case` compare fairly.

### CLI flags
`StatisticsConfig.override(**flags)` applies CLI flags on top of the YAML `statistics:` block. It skips flags that weren't given and validates the rest the same way the YAML is validated. The Typer options that call it arrive with `agentprobe run` (D1.1) and `agentprobe compare` (D2.1).

### Power limit
At n runs per case, the smallest possible one-sided Fisher p is 1 / C(2n, n). Holm's first step multiplies it by m, the number of compared cases. So a single case can be flagged only when m ≤ `alpha`·C(2n, n):

| Runs per case | Smallest p | Largest m with a possible per-case flag |
|---|---|---|
| 3 | 1/20 | 1 |
| 5 | 1/252 | 12 |
| 6 | 1/924 | 46 |
| 8 | 1/12,870 | 643 |
| 10 | 1/184,756 | 9,237 |

At 5 runs and 30 cases, a deterministic break of one case (5/5 → 0/5) is never flagged per case. It is also not flagged at suite level, because one changed case gives a sign-flip p of 1/2. [docs/metrics.md](../metrics.md) measures the detection rates.

Considered but not adopted (it changes the approved method, so it needs a decision): Tarone's (1990) modification for discrete tests.
- It leaves out of the family any test whose smallest achievable p can't reach `alpha`/m′, and still controls the FWER at `alpha`.
- Here it would restore single-case detection, because unchanged deterministic cases (5/5 vs 5/5 has a smallest p of 1) drop out of the family.
- Raising `runs_per_case` also works.

## Consequences
- The executor (B1.7) builds one `CaseSummary` per case. `run_case_summaries` maps onto it column for column: `passes`, `attempts`, `pass_rate`, `label`, `mean_score`, `mean_latency_ms` and `total_cost` (as `cost_usd`).
- All outputs are frozen dataclasses. `dataclasses.asdict` makes them JSON-ready for the compare endpoint (B2.5) and the CLI.
- Hypothesis (`hypothesis==6.168.1`) is a workspace dev dependency. `packages/core/tests/stats/conftest.py` loads a derandomized profile with no example database and no deadline, so the property tests are deterministic.
- `scripts/measure_false_alarms.py` and [docs/metrics.md](../metrics.md) measure the false-alarm rate and the detection power. They are the source for the SPEC.md §15 metric.
