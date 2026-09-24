# Measured metrics

These are numbers for the README and SPEC.md §15. Each one says how it was measured and under which assumptions.

## False regression alarms: multi-run statistics vs single-run checks

### Result
In a seeded simulation of flaky agents that did **not** change (30 cases × 5 runs per case, 20% of cases flaky):
- A naive single-run pass/fail check raised a false regression alarm on **70.6%** of runs.
- AgentProbe's multi-run statistical check raised one on **0.7%** of runs.

That is a **99.0% reduction** (98.6–99.3%, derived from the two rates' 95% intervals). Against a single run that retries failures once, the reduction is 98.3% (39.0% → 0.7%).

The same simulation measured detection of real regressions, which comes with this trade-off:
- **Broad regressions are caught.** When every case gets 10% worse, the statistical check detects it on 85.8% of runs.
- **A single broken case usually isn't.** When one of 30 deterministic cases breaks completely, the statistical check detects it on only 4.1% of runs at 5 runs per case. The naive check catches it every time, although 70.6% of its alarms on unchanged agents are false.
- **More runs per case fix this.** At 10 runs per case, single-case detection goes back to 100% and the false-alarm rate stays at 0.3%.

This limit is a property of the approved method, not a bug. See [ADR 0014](decisions/0014-statistics-implementation.md#power-limit) and [the power section below](#detection-power-the-other-half-of-the-trade-off).

Suggested resume wording, which stays true only with its conditions attached:
> Cut false regression alarms by 99% (70.6% → 0.7% of unchanged runs) versus single-run pass/fail checks, in a seeded simulation of flaky LLM agents (30 cases × 5 runs, 20% flaky cases).

### What is measured
A false alarm is a regression verdict on an agent whose true behavior did not change. Each trial:
1. Draws an agent: a true pass probability for every case.
2. Runs it twice from those same probabilities: once as the baseline, once as the candidate.
3. Asks each check whether it sees a regression.

Every check sees the same simulated attempts. The single-run checks use only the first attempt, or the first two when a failure is retried.

5,000 trials per cell. Rates come with 95% Wilson intervals. The seed is fixed (20260924), so the tables below are exactly what the script prints.

### Checks compared
| Check | Agent calls per case | Rule |
|---|---|---|
| Naive single run | 1 | Alarm if any case passed on the baseline and fails on the candidate. This is a normal CI test gate. |
| Single run, failures retried once | 1–2 | The same rule, but a case counts as passed if either of its first two attempts passed (pytest-rerunfailures style). |
| N runs, no statistics | N | Alarm if any case's pass count went down. |
| N runs, effect size only | N | Alarm if the suite's mean pass rate fell by at least `min_drop` (0.05). There is no significance test. |
| N runs, AgentProbe statistical check | N | `compare_runs(...).verdict == "regression"` with the shipped defaults (`alpha` 0.05, `min_drop` 0.05). It uses Fisher exact tests with Holm correction per case, a sign-flip permutation test on the shared cases, and `min_drop` on both ([ADR 0006](decisions/0006-statistics-methodology.md), [ADR 0014](decisions/0014-statistics-implementation.md)). |

The two middle rows separate the effect of running more times from the effect of the statistics.

### Model and assumptions
These parameters were fixed before the first run and were not changed afterwards. Where a choice was a judgment call, the conservative option was taken, meaning the one that makes the naive check look better and the reduction smaller.

**Agent model.** Each case is either deterministic (true pass probability exactly 1) or flaky, with a true pass probability drawn from Uniform(0.5, 0.95) for each trial. A case's attempts are independent draws at its probability.
- *Why:* regression suites mostly hold cases that normally pass. A flaky case that usually fails would be tracked as a known failure. The demo support bot's order lookups (`FLAKY_RATE = 0.2`, so p = 0.8) fall inside this range.
- *Conservative choice:* deterministic cases never flake. Real "stable" LLM cases fail occasionally (p ≈ 0.99), which would add false alarms to the naive check only.

**Suite size: 30 cases.** A small-to-medium agent regression suite. The sensitivity section also covers 10 and 100 cases.

**Runs per case: 5.** The value in SPEC.md §15 and in the example suite (`suites/examples/support-agent-safety.yaml`). The sensitivity section also covers 3 and 10.

**Flaky fraction: 20%.**
- *Context for the choice:* in conventional software, Google reported that about 16% of its tests showed some flakiness, and about 1.5% of all test runs gave a flaky result (Micco, "Flaky Tests at Google and How We Mitigate Them", Google Testing Blog, 2016). LLM agents are much less deterministic than that. τ-bench (Yao et al., 2024) reports gpt-4o succeeding on fewer than 50% of retail tasks, and passing all 8 of 8 repeated trials (pass^8) on fewer than 25%.
- *Sensitivity:* the section below also covers 5%, 10% and 40%.

**Thresholds.** The shipped defaults: `alpha` = 0.05, `min_drop` = 0.05, 10,000 permutation draws. With equal attempts per case, every test here runs on the exact path, so the draw count is never used.

**Planted regressions,** applied to the candidate only and always to deterministic cases, so the change is not hidden inside existing flakiness:
- one case breaks: its p goes from 1 to 0;
- three cases turn flaky: their p goes from 1 to 0.5;
- every case gets 10% worse: every p becomes 0.9·p.

A check of the model against theory: with k flaky cases, the naive check's expected false-alarm rate is 1 − (1 − E[p(1 − p)])^k, where p ~ U(0.5, 0.95) and E[p(1 − p)] = 0.1825.
- Reference scenario (k = 6): theory gives 70.2%; the simulation measured 70.6%.
- Seven of the eight rows below are within 1.6 standard errors of theory.
- The exception is the "10% flaky" row, at 42.9% against 45.4% (−3.5 SE). Six other seeds gave 44.2–46.2% for that cell (mean 45.3%), so it is an unlucky draw of the fixed seed, not a model error. It is left as printed rather than re-seeded, because picking seeds would be tuning.

### Results (reference scenario: 30 cases, 5 runs per case, 20% flaky)
| Check | False alarms (no change) | One case breaks (1 → 0) | Three cases turn flaky (1 → 0.5) | Every case 10% worse (p → 0.9p) |
|---|---|---|---|---|
| Naive single run: any case pass → fail | 70.6% (69.3–71.8) | 100.0% (99.9–100.0) | 96.3% (95.8–96.8) | 98.3% (97.9–98.7) |
| Single run, failures retried once | 39.0% (37.6–40.3) | 100.0% (99.9–100.0) | 73.8% (72.6–75.0) | 62.4% (61.0–63.7) |
| N runs, no statistics: any case's pass count fell | 92.1% (91.3–92.8) | 100.0% (99.9–100.0) | 100.0% (99.9–100.0) | 100.0% (99.9–100.0) |
| N runs, effect size only: suite mean fell ≥ min_drop | 1.4% (1.1–1.8) | 22.5% (21.3–23.6) | 50.9% (49.5–52.2) | 91.7% (90.9–92.4) |
| N runs, AgentProbe statistical check | **0.7% (0.5–0.9)** | 4.1% (3.5–4.6) | 20.2% (19.1–21.4) | 85.8% (84.8–86.7) |

False-alarm reduction of the statistical check:
- vs the naive single run: **99.0%** (98.6–99.3);
- vs a single run with one retry: 98.3% (97.5–98.8).

### Sensitivity: false alarms (no change)
| Scenario | Naive single run | Single run + retry | N runs, no statistics | N runs, effect size only | N runs, statistical | Reduction vs naive |
|---|---|---|---|---|---|---|
| **Reference** (30 cases, 5 runs, 20% flaky) | 70.6% (69.3–71.8) | 39.0% (37.6–40.3) | 92.1% (91.3–92.8) | 1.4% (1.1–1.8) | 0.7% (0.5–0.9) | 99.0% (98.6–99.3) |
| 5% flaky | 34.2% (32.9–35.6) | 14.2% (13.3–15.2) | 56.0% (54.7–57.4) | 0.0% (0.0–0.1) | 0.0% (0.0–0.1) | 100.0% (99.8–100.0) |
| 10% flaky | 42.9% (41.5–44.2) | 21.2% (20.1–22.4) | 69.6% (68.4–70.9) | 0.1% (0.1–0.3) | 0.0% (0.0–0.1) | 100.0% (99.8–100.0) |
| 40% flaky | 90.6% (89.8–91.4) | 62.0% (60.6–63.3) | 99.4% (99.1–99.6) | 5.2% (4.6–5.9) | 2.8% (2.4–3.3) | 96.9% (96.3–97.4) |
| 10 cases | 32.5% (31.3–33.9) | 15.1% (14.2–16.2) | 54.9% (53.5–56.3) | 9.0% (8.3–9.8) | 0.1% (0.0–0.2) | 99.8% (99.3–99.9) |
| 100 cases | 98.2% (97.8–98.6) | 80.8% (79.7–81.9) | 100.0% (99.9–100.0) | 0.0% (0.0–0.1) | 0.0% (0.0–0.1) | 100.0% (99.9–100.0) |
| 3 runs per case | 70.2% (68.9–71.5) | 39.6% (38.2–40.9) | 87.0% (86.0–87.9) | 4.1% (3.6–4.7) | 0.6% (0.4–0.9) | 99.1% (98.7–99.4) |
| 10 runs per case | 70.0% (68.7–71.2) | 37.3% (36.0–38.7) | 95.4% (94.8–96.0) | 0.2% (0.1–0.3) | 0.3% (0.2–0.5) | 99.5% (99.2–99.7) |

Every row except the reference changes one parameter from the reference.

### Sensitivity: detection of planted regressions (naive / statistical)
| Scenario | One case breaks (1 → 0) | Three cases turn flaky (1 → 0.5) | Every case 10% worse (p → 0.9p) |
|---|---|---|---|
| **Reference** (30 cases, 5 runs, 20% flaky) | 100.0% / 4.1% | 96.3% / 20.2% | 98.3% / 85.8% |
| 5% flaky | 100.0% / 0.0% | 91.0% / 9.6% | 96.9% / 95.9% |
| 10% flaky | 100.0% / 0.0% | 93.3% / 16.5% | 97.7% / 94.2% |
| 40% flaky | 100.0% / 6.7% | 99.0% / 19.0% | 99.2% / 69.2% |
| 10 cases | 100.0% / 100.0% | 92.1% / 18.7% | 75.4% / 29.2% |
| 100 cases | 100.0% / 0.1% | 99.7% / 0.3% | 100.0% / 99.6% |
| 3 runs per case | 100.0% / 2.6% | 96.6% / 14.8% | 98.6% / 65.3% |
| 10 runs per case | 100.0% / 100.0% | 96.1% / 57.8% | 98.2% / 97.5% |

### Reading the results
**Where the reduction comes from.** Running more times without statistics makes things worse: with 5 runs there are more chances to see some case dip, so the false-alarm rate rises from 70.6% to 92.1%. What removes most of the false alarms at 30 cases is judging the suite mean against `min_drop` (70.6% → 1.4%). The significance tests keep the rate low where that rule alone fails:
- small suites (10 cases): 9.0% → 0.1%;
- very flaky suites (40% flaky): 5.2% → 2.8%;
- few runs (3 runs per case): 4.1% → 0.6%.

The statistical check stays under its documented bound of 2·`alpha` = 10% everywhere (at most 2.8%). The effect-size-only rule has no such bound.

**Cost.** The multi-run checks make 5× the agent calls of a single run. The single-run-with-retry row shows how far a cheap mitigation gets: 39.0% false alarms.

### Detection power: the other half of the trade-off
A check that never fires has no false alarms, so the false-alarm rate means little without the detection rate beside it.
- **Localized regressions are hard to detect at 5 runs per case.** With 5 runs, the smallest possible per-case p-value is 1/252. Holm's correction multiplies it by the number of compared cases, so with more than 12 cases no single case can be flagged, however badly it breaks. The suite-level test can't help either, because one changed case gives a sign-flip p of 1/2. That explains the 4.1% detection rate in the reference scenario, and the 100% rate at 10 cases or at 10 runs per case. Three cases turning 50% flaky is weak evidence at 5 runs no matter which valid test is used.
- **Widespread regressions are detected well**, and better as suites grow: 85.8% at 30 cases and 99.6% at 100 cases for a 10% degradation across the board.
- **The naive check's detection rates don't mean what they seem to.** Its 100% on a broken case sits next to a 70.6% false-alarm rate on unchanged agents, so most of its alarms say nothing.

**How to catch single-case breaks.** Either raise `runs_per_case`, or adopt a discrete-aware multiple-testing correction:
- At 6 runs, a single broken case can be flagged in suites of up to 46 cases; at 8 runs, up to 643 cases.
- Tarone's modification is described in ADR 0014. It would change the approved method, so it is left for a decision.

### Limitations of the simulation
- Cases are independent, and a flaky case's pass probability is the same in both runs. Real agent failures can be correlated across cases, for example a provider outage during one run. That would raise every check's false-alarm rate, the statistical check's included.
- Judges are assumed perfect: a pass is a true pass. Judge noise adds flakiness, which the flaky fraction stands in for.
- The distribution of flaky pass rates, Uniform(0.5, 0.95), is an assumption. The naive rate depends on E[p(1 − p)], which is symmetric around 0.5, so mostly-failing flaky cases would give similar results.
- These are simulated runs, not measurements of real agents. Once the executor (B1.7) and the demo agents run end to end, the same comparison can be repeated on recorded runs of the demo agents.

### Reproduce
```bash
uv run python scripts/measure_false_alarms.py            # 5,000 trials per cell, seed 20260924
uv run python scripts/measure_false_alarms.py --trials 500 --seed 1   # quicker, different draws
```
The script prints the tables above as Markdown. It runs offline in about 3 minutes and calls no LLM.
