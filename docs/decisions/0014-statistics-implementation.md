# 0014: Statistics implementation

Status: accepted (2026-09-24). Amended twice, both user decisions:
- 2026-09-24: the per-case correction is Tarone–Holm, not plain Holm (see [Per-case tests](#per-case-tests)).
- 2026-09-26: `alpha` is the budget for the whole verdict and is split over the per-case family and the suite test, so the verdict's false-alarm rate is held at `alpha` instead of 2·`alpha` (see [Verdict](#verdict)).

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

**Procedure** (`significance.tarone_holm`), run at `alpha_cases` (the per-case channel's share of the budget; `alpha` below means that share):
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
- `regression` if at least one case is flagged worse, or the suite is. A case is flagged when the Tarone–Holm step-down rejects it at `alpha_cases` AND its own pass rate dropped by at least `min_drop`.
- **A flagged case is enough on its own**, even when the suite's mean drop is below `min_drop` and the suite test isn't significant. One broken case in 30 moves the suite mean by only 1/30 = 0.033.
- The demo scenario is a test (`test_demo_one_refund_case_breaking_in_30_is_a_regression`), with and without flaky cases around it: support-bot v2's refund case goes 5/5 → 0/5 in a 30-case suite. The verdict is `regression`, the refund case is compared against the whole per-case budget (K = 1, threshold 0.025, p = 1/252 = 0.0040), the suite drop is under `min_drop`, and the suite test isn't significant. The split leaves room here: this case would stay flagged up to K = 6.
- Otherwise `improvement` if any case or the suite is flagged better, by the mirror rule.
- Otherwise `no_change`.
- A regression wins over an improvement, because a regression is what a CI gate has to catch.

**The `alpha` budget is split over the two channels (amended 2026-09-26, user decision).**

A verdict fires when the per-case family OR the suite test fires. Running both at `alpha` made the verdict's own false-alarm rate as high as 2·`alpha` by the union bound, and the simulation measured 6.5% against a configured 5% — so the number users actually gate on was not the number they configured.

`alpha` is now the budget for the **verdict**, split between the channels by Bonferroni:
- `alpha_cases` (default `alpha`/2) is what the Tarone–Holm step-down is run at;
- `alpha_suite` (default `alpha`/2) is what the sign-flip p-value is compared against;
- each is a `StatisticsConfig` field, so a suite can spend the budget unevenly (all of it on the per-case family, say). Their sum may not exceed `alpha`; the config refuses it, since that is exactly the bound being claimed. Raising `alpha` is how to buy power for both.

Why a plain Bonferroni split rather than something sharper: the two channels are strongly dependent (both read the same per-case deltas), so the union bound is loose and the true rate lands well under `alpha`. A sharper split would need the dependence structure, which varies with the suite's flakiness and size. Bonferroni needs no assumptions and is conservative in the safe direction, and `docs/metrics.md` measures how much is left on the table.

**Error rate: what is proven, and what is measured.**
- **The verdict's false-alarm rate is at most `alpha`.** Each channel holds its own rate at its share (below), and a verdict is their union, so the total is at most `alpha_cases` + `alpha_suite` = `alpha`. Measured across suite sizes 5/13/30/100 and five flakiness levels in `test_family_wise_error.py` and `docs/metrics.md`.
- **The per-case family's false-alarm rate is at most `alpha_cases`.** This follows from the argument above with `alpha_cases` in place of `alpha`, and is checked two ways:
  - *Exactly*, by enumerating every joint outcome for small families (up to 3 cases at up to 4 runs from Hypothesis-drawn true rates, plus 3 cases at 5 runs). These drive `tarone_holm` at a given level, so they prove the procedure for any budget it is handed; at 0.05, true rates 1/2, 9/10 and 19/20 with 5 runs give exactly 1.10%.
  - *By seeded simulation* (`test_family_wise_error.py`, 1,000 trials per cell) at the shipped `alpha_cases` of 0.025: suite sizes 5, 13, 30 and 100 × 20% / 50% / 100% flaky, every case at a different true rate (0.05–0.95), and every case a coin flip, plus 3 and 10 runs per case. The highest rate measured across that grid is 1.5%.
- **The suite test's false-alarm rate is at most `alpha_suite`.** The sign-flip test is exact conditional on the observed |deltas|: with equal attempts per case each delta is symmetric about 0, so under the null its sign is ±1 with probability 1/2 independently of its size, which is precisely the permutation null. The `min_drop` filter only removes flags. Measured at 2.1% (5,000 trials, 100 coin-flip cases) against a budget of 2.5%.

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

**With Tarone–Holm.** Unchanged deterministic cases (min p = 1) leave the family, so a single break is flagged at any suite size. A test covers 5 to 500 cases at 5 and 10 runs. Measured in [docs/metrics.md](../metrics.md), reference scenario:

| | Holm | Tarone–Holm at `alpha` | Tarone–Holm, `alpha` split (shipped) |
|---|---|---|---|
| One broken case detected | 4.1% | 100% | **100%** |
| Three cases turning flaky detected | 20.2% | 38.5% | 21.1% |
| Every case 10% worse detected | 85.8% | 86.0% | 77.7% |
| False alarms | 0.7% | 2.3% | **0.9%** |
| Worst verdict false alarms, calibration grid | — | 6.5% (above `alpha`) | **2.8%** |

**What the split costs, measured** (it was predicted analytically here before the change, and the prediction held):
- **At 5 runs the demo break is unaffected.** One case going 5/5 → 0/5 (p = 1/252 = 0.0040) is still compared against the whole 0.025 per-case budget, because Tarone drops every unchanged case from the family. Detection stays 100% at 10 and 30 cases. It would take K > 6 competing cases to lose it.
- **At 100 cases it slips to 99.2%** (from 100%): with 20 flaky cases, some draws put six or more of them within reach of 0.025, so K reaches 7 and the threshold (0.0036) falls below p.
- **At 3 runs a single break can no longer be flagged** (38.4% → 0.5%, the remainder coming from the suite channel). Its smallest possible p is 1/20, above the 0.025 share. This is the one real loss, and the reason the CLI's `--help` tells users to run 5 or more times.

**Remaining limits, documented and tested:**
- **At 3 runs per case**, a break has p = 1/20, twice the default per-case share, so it can never be flagged. Use 5 or more runs.
- **A case that only turns flaky** (5/5 → 3/5, p = 56/252) is weak evidence at 5 runs whatever the correction. More runs per case, or several cases moving together, are what catch it.
- **1 or 2 attempts per case** can never flag a case. The smallest p values there are 1/2 and 1/6.

## Consequences
- The executor (B1.7) builds one `CaseSummary` per case. `run_case_summaries` maps onto it column for column: `passes`, `attempts`, `pass_rate`, `label`, `mean_score`, `mean_latency_ms` and `total_cost` (as `cost_usd`).
- All outputs are frozen dataclasses. `dataclasses.asdict` makes them JSON-ready for the compare endpoint (B2.5) and the CLI.
- `compare_cases()` runs the per-case family on its own. `compare_runs()` uses it, and the family-wise error test calls it directly.
- `test_family_wise_error.py` adds about 21 s to `pnpm check` (12 s before it also measured the suite channel and the combined verdict). That is the price of a seeded proof across 24 scenarios, which the user asked to be a test rather than only a script. It drives `compare_runs` once per trial and reads all three rates off the one report, rather than simulating each channel separately.
- The per-cell bar is the point estimate for the combined verdict and the Wilson upper bound for each channel. At 1,000 trials a Wilson bound on a ~3% rate reaches ~4.8%, so asserting it per cell against `alpha` would make the test a coin flip; a pooled bound over all 20 cells (20,000 trials) supplies the confidence instead.
- Hypothesis (`hypothesis==6.168.1`) is a workspace dev dependency. `packages/core/tests/stats/conftest.py` loads a derandomized profile with no example database and no deadline, so the property tests are deterministic.
- `scripts/measure_false_alarms.py` and [docs/metrics.md](../metrics.md) measure the false-alarm rate and the detection power. They are the source for the SPEC.md §15 metric.
