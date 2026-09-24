# Measured metrics

These are numbers for the README and SPEC.md §15. Each one says how it was measured and under which assumptions.

## False regression alarms: multi-run statistics vs single-run checks

### Result
In a seeded simulation of flaky agents that did **not** change (30 cases × 5 runs per case, 20% of cases flaky):
- A naive single-run pass/fail check raised a false regression alarm on **70.6%** of runs.
- AgentProbe's multi-run statistical check raised one on **2.3%** of runs.

That is a **96.7% reduction** (96.0–97.3%, derived from the two rates' 95% intervals). Against a single run that retries failures once, the reduction is 94.1% (39.0% → 2.3%).

The same simulation measured detection of real regressions. With the shipped per-case correction (Tarone–Holm), when one of 30 deterministic cases breaks completely, the statistical check catches it on **100%** of runs, as the naive check does. When every case gets 10% worse, it catches 86.0%.

**With and without Tarone.** The first version of this page reported a 99.0% reduction. That came from plain Holm per case, which almost never caught a single broken case (4.1%). Tarone's correction ([ADR 0014](decisions/0014-statistics-implementation.md#per-case-tests)) trades a little of that reduction for catching it:

| Reference scenario | Holm per case (before) | Tarone–Holm per case (shipped) |
|---|---|---|
| False alarms, agent unchanged | 0.7% (0.5–0.9) | 2.3% (1.9–2.8) |
| Reduction vs naive single run | 99.0% (98.6–99.3) | **96.7% (96.0–97.3)** |
| Reduction vs single run + retry | 98.3% (97.5–98.8) | 94.1% (92.7–95.2) |
| One case breaks (1 → 0): detected | 4.1% | **100.0%** |
| Three cases turn flaky (1 → 0.5): detected | 20.2% | 38.5% |
| Every case 10% worse: detected | 85.8% | 86.0% |

The 96.7% figure is the honest headline, because it comes with a check that still catches single-case breaks.

Suggested resume wording, which stays true only with its conditions attached:
> Cut false regression alarms by 97% (70.6% → 2.3% of unchanged runs) versus single-run pass/fail checks while still catching every single-case break, in a seeded simulation of flaky LLM agents (30 cases × 5 runs per case, 20% flaky cases).

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
| N runs, statistical, Holm per case (before) | N | As below, but plain Holm across cases. Computed with production code: Tarone–Holm with every minimum p set to 0 is exactly Holm, and a unit test proves it. |
| N runs, statistical, Tarone–Holm per case (shipped) | N | `compare_runs(...).verdict == "regression"` with the shipped defaults (`alpha` 0.05, `min_drop` 0.05). It uses one-sided Fisher exact tests with a Tarone–Holm step-down per case, a sign-flip permutation test on the shared cases, and `min_drop` on both ([ADR 0006](decisions/0006-statistics-methodology.md), [ADR 0014](decisions/0014-statistics-implementation.md)). |

The "no statistics" and "effect size only" rows separate the effect of running more times from the effect of the statistics.

### Model and assumptions
These parameters were fixed before the first run and were not changed afterwards, including when Tarone's correction was added. Where a choice was a judgment call, the conservative option was taken, meaning the one that makes the naive check look better and the reduction smaller.

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
- Seven of the eight naive rates below are within 1.6 standard errors of theory.
- The exception is the "10% flaky" row, at 42.9% against 45.4% (−3.5 SE). Six other seeds gave 44.2–46.2% for that cell (mean 45.3%), so it is an unlucky draw of the fixed seed, not a model error. It is left as printed rather than re-seeded, because picking seeds would be tuning.

### Results (reference scenario: 30 cases, 5 runs per case, 20% flaky)
| Check | False alarms (no change) | One case breaks (1 → 0) | Three cases turn flaky (1 → 0.5) | Every case 10% worse (p → 0.9p) |
|---|---|---|---|---|
| Naive single run: any case pass → fail | 70.6% (69.3–71.8) | 100.0% (99.9–100.0) | 96.3% (95.8–96.8) | 98.3% (97.9–98.7) |
| Single run, failures retried once | 39.0% (37.6–40.3) | 100.0% (99.9–100.0) | 73.8% (72.6–75.0) | 62.4% (61.0–63.7) |
| N runs, no statistics: any case's pass count fell | 92.1% (91.3–92.8) | 100.0% (99.9–100.0) | 100.0% (99.9–100.0) | 100.0% (99.9–100.0) |
| N runs, effect size only: suite mean fell ≥ min_drop | 1.4% (1.1–1.8) | 22.5% (21.3–23.6) | 50.9% (49.5–52.2) | 91.7% (90.9–92.4) |
| N runs, statistical, Holm per case (before) | 0.7% (0.5–0.9) | 4.1% (3.5–4.6) | 20.2% (19.1–21.4) | 85.8% (84.8–86.7) |
| N runs, statistical, Tarone–Holm per case (shipped) | **2.3% (1.9–2.8)** | **100.0% (99.9–100.0)** | 38.5% (37.1–39.8) | 86.0% (85.0–86.9) |

### With and without Tarone, across scenarios
Every row except the reference changes one parameter from the reference.

| Scenario | Naive FA | Holm FA | Tarone–Holm FA | Reduction vs naive, Holm | Reduction vs naive, Tarone–Holm | One case breaks, detected: naive / Holm / Tarone–Holm |
|---|---|---|---|---|---|---|
| **Reference** (30 cases, 5 runs, 20% flaky) | 70.6% (69.3–71.8) | 0.7% (0.5–0.9) | 2.3% (1.9–2.8) | 99.0% (98.6–99.3) | **96.7% (96.0–97.3)** | 100.0% / 4.1% / 100.0% |
| 5% flaky | 34.2% (32.9–35.6) | 0.0% (0.0–0.1) | 0.9% (0.7–1.2) | 100.0% (99.8–100.0) | 97.3% (96.3–98.1) | 100.0% / 0.0% / 100.0% |
| 10% flaky | 42.9% (41.5–44.2) | 0.0% (0.0–0.1) | 1.3% (1.0–1.6) | 100.0% (99.8–100.0) | 97.0% (96.1–97.7) | 100.0% / 0.0% / 100.0% |
| 40% flaky | 90.6% (89.8–91.4) | 2.8% (2.4–3.3) | 3.7% (3.2–4.3) | 96.9% (96.3–97.4) | 95.9% (95.3–96.5) | 100.0% / 6.7% / 100.0% |
| 10 cases | 32.5% (31.3–33.9) | 0.1% (0.0–0.2) | 0.9% (0.6–1.2) | 99.8% (99.3–99.9) | 97.4% (96.3–98.1) | 100.0% / 100.0% / 100.0% |
| 100 cases | 98.2% (97.8–98.6) | 0.0% (0.0–0.1) | 0.8% (0.6–1.1) | 100.0% (99.9–100.0) | 99.2% (98.9–99.4) | 100.0% / 0.1% / 100.0% |
| 3 runs per case | 70.2% (68.9–71.5) | 0.6% (0.4–0.9) | 3.1% (2.6–3.6) | 99.1% (98.7–99.4) | 95.6% (94.8–96.3) | 100.0% / 2.6% / 38.4% |
| 10 runs per case | 70.0% (68.7–71.2) | 0.3% (0.2–0.5) | 2.1% (1.8–2.6) | 99.5% (99.2–99.7) | 96.9% (96.2–97.5) | 100.0% / 100.0% / 100.0% |

### Sensitivity: false alarms of every check (no change)
| Scenario | Naive single run | Single run + retry | N runs, no statistics | N runs, effect size only | Holm (before) | Tarone–Holm (shipped) |
|---|---|---|---|---|---|---|
| **Reference** | 70.6% (69.3–71.8) | 39.0% (37.6–40.3) | 92.1% (91.3–92.8) | 1.4% (1.1–1.8) | 0.7% (0.5–0.9) | 2.3% (1.9–2.8) |
| 5% flaky | 34.2% (32.9–35.6) | 14.2% (13.3–15.2) | 56.0% (54.7–57.4) | 0.0% (0.0–0.1) | 0.0% (0.0–0.1) | 0.9% (0.7–1.2) |
| 10% flaky | 42.9% (41.5–44.2) | 21.2% (20.1–22.4) | 69.6% (68.4–70.9) | 0.1% (0.1–0.3) | 0.0% (0.0–0.1) | 1.3% (1.0–1.6) |
| 40% flaky | 90.6% (89.8–91.4) | 62.0% (60.6–63.3) | 99.4% (99.1–99.6) | 5.2% (4.6–5.9) | 2.8% (2.4–3.3) | 3.7% (3.2–4.3) |
| 10 cases | 32.5% (31.3–33.9) | 15.1% (14.2–16.2) | 54.9% (53.5–56.3) | 9.0% (8.3–9.8) | 0.1% (0.0–0.2) | 0.9% (0.6–1.2) |
| 100 cases | 98.2% (97.8–98.6) | 80.8% (79.7–81.9) | 100.0% (99.9–100.0) | 0.0% (0.0–0.1) | 0.0% (0.0–0.1) | 0.8% (0.6–1.1) |
| 3 runs per case | 70.2% (68.9–71.5) | 39.6% (38.2–40.9) | 87.0% (86.0–87.9) | 4.1% (3.6–4.7) | 0.6% (0.4–0.9) | 3.1% (2.6–3.6) |
| 10 runs per case | 70.0% (68.7–71.2) | 37.3% (36.0–38.7) | 95.4% (94.8–96.0) | 0.2% (0.1–0.3) | 0.3% (0.2–0.5) | 2.1% (1.8–2.6) |

### Sensitivity: detection of planted regressions (naive / Holm / Tarone–Holm)
| Scenario | One case breaks (1 → 0) | Three cases turn flaky (1 → 0.5) | Every case 10% worse (p → 0.9p) |
|---|---|---|---|
| **Reference** | 100.0% / 4.1% / 100.0% | 96.3% / 20.2% / 38.5% | 98.3% / 85.8% / 86.0% |
| 5% flaky | 100.0% / 0.0% / 100.0% | 91.0% / 9.6% / 46.0% | 96.9% / 95.9% / 96.0% |
| 10% flaky | 100.0% / 0.0% / 100.0% | 93.3% / 16.5% / 45.1% | 97.7% / 94.2% / 94.3% |
| 40% flaky | 100.0% / 6.7% / 100.0% | 99.0% / 19.0% / 28.1% | 99.2% / 69.2% / 69.7% |
| 10 cases | 100.0% / 100.0% / 100.0% | 92.1% / 18.7% / 46.8% | 75.4% / 29.2% / 30.5% |
| 100 cases | 100.0% / 0.1% / 100.0% | 99.7% / 0.3% / 9.7% | 100.0% / 99.6% / 99.6% |
| 3 runs per case | 100.0% / 2.6% / 38.4% | 96.6% / 14.8% / 24.7% | 98.6% / 65.3% / 66.3% |
| 10 runs per case | 100.0% / 100.0% / 100.0% | 96.1% / 57.8% / 83.2% | 98.2% / 97.5% / 97.5% |

### Null calibration: which part of the check raises false alarms
1,000 trials per cell, 5 runs per case, nothing changed. The "different rates" scenario gives every case its own true pass rate, spread evenly over 0.05–0.95. The per-case family's bound is also a unit test (`packages/core/tests/stats/test_family_wise_error.py`), with its own seeds.

| Scenario | Cases | Per-case family (Tarone–Holm) | Whole verdict (family + suite test) |
|---|---|---|---|
| 20% flaky | 5 | 0.2% (0.1–0.7) | 0.2% (0.1–0.7) |
| 20% flaky | 13 | 0.8% (0.4–1.6) | 0.8% (0.4–1.6) |
| 20% flaky | 30 | 2.7% (1.9–3.9) | 3.3% (2.4–4.6) |
| 20% flaky | 100 | 0.9% (0.5–1.7) | 0.9% (0.5–1.7) |
| 50% flaky | 5 | 1.0% (0.5–1.8) | 1.0% (0.5–1.8) |
| 50% flaky | 13 | 1.9% (1.2–2.9) | 2.7% (1.9–3.9) |
| 50% flaky | 30 | 0.7% (0.3–1.4) | 2.9% (2.0–4.1) |
| 50% flaky | 100 | 2.1% (1.4–3.2) | 2.9% (2.0–4.1) |
| all flaky | 5 | 1.8% (1.1–2.8) | 2.2% (1.5–3.3) |
| all flaky | 13 | 1.2% (0.7–2.1) | 4.5% (3.4–6.0) |
| all flaky | 30 | 1.0% (0.5–1.8) | 4.9% (3.7–6.4) |
| all flaky | 100 | 2.4% (1.6–3.5) | **6.2% (4.9–7.9)** |
| different rates | 5 | 1.5% (0.9–2.5) | 1.5% (0.9–2.5) |
| different rates | 13 | 0.9% (0.5–1.7) | 3.2% (2.3–4.5) |
| different rates | 30 | 0.9% (0.5–1.7) | 4.4% (3.3–5.9) |
| different rates | 100 | 2.4% (1.6–3.5) | **6.5% (5.1–8.2)** |
| all coin flips | 5 | 0.9% (0.5–1.7) | 1.9% (1.2–2.9) |
| all coin flips | 13 | 1.4% (0.8–2.3) | 4.7% (3.6–6.2) |
| all coin flips | 30 | 2.8% (1.9–4.0) | **6.2% (4.9–7.9)** |
| all coin flips | 100 | 0.0% (0.0–0.4) | **5.2% (4.0–6.8)** |

- **The per-case family stays under `alpha` everywhere** (at most 2.8%). That is guaranteed by the method and checked exactly in unit tests.
- **The whole verdict can exceed `alpha` on heavily flaky suites** (up to 6.5%, in bold above). It adds the suite-level test, which is also held at `alpha`, so its worst case is 2·`alpha` = 10%.
  - In the realistic 20%-flaky scenario it stays at 0.2–3.3%.
  - Holding the verdict itself at `alpha` would mean splitting `alpha` between the two tests. That is an open decision ([ADR 0014](decisions/0014-statistics-implementation.md#verdict)).

### Reading the results
**Where the reduction comes from.** Running more times without statistics makes things worse: with 5 runs there are more chances to see some case dip, so the false-alarm rate rises from 70.6% to 92.1%.

At 30 cases, judging the suite mean against `min_drop` alone gives few false alarms (1.4%, fewer than the shipped check's 2.3%). But it has two problems:
- **It misses localized breaks.** It catches one broken case only 22.5% of the time.
- **Its rate has no bound.** It reaches 9.0% at 10 cases, against 0.9% for the shipped check.

The significance tests are what keep false alarms bounded across suite sizes and flakiness levels, while still letting a single flagged case trigger a regression.

**Cost.** The multi-run checks make 5× the agent calls of a single run. The single-run-with-retry row shows how far a cheap mitigation gets: 39.0% false alarms.

### Detection power: the other half of the trade-off
A check that never fires has no false alarms, so the false-alarm rate means little without the detection rate beside it.
- **Single broken cases are caught at 5 or more runs per case.** Detection is 100% at every suite size simulated (10, 30 and 100 cases) and every flakiness level. Tarone's correction drops unchanged deterministic cases (their smallest possible p is 1) from the multiple-testing family, so one case going 5/5 → 0/5 (p = 1/252) is compared against `alpha` itself.
- **At 3 runs per case, a break is caught only 38.4% of the time.** Its p-value is 1/20, exactly `alpha`, so any other case whose margins could also reach `alpha` makes the correction stricter than that. Use 5 or more runs.
- **Cases that only turn flaky are weak evidence at 5 runs.** Three cases dropping to a 50% pass rate are detected 38.5% of the time (83.2% at 10 runs). A single 5/5 → 3/5 case has p = 56/252, far from significant under any correction.
- **Widespread regressions are detected well**, and better as suites grow: 86.0% at 30 cases and 99.6% at 100 cases for a 10% degradation across the board.
- **The naive check's detection rates don't mean what they seem to.** Its 100% on a broken case sits next to a 70.6% false-alarm rate on unchanged agents, so most of its alarms say nothing.

### Limitations of the simulation
- Cases are independent, and a flaky case's pass probability is the same in both runs. Real agent failures can be correlated across cases, for example a provider outage during one run. That would raise every check's false-alarm rate, the statistical check's included.
- Judges are assumed perfect: a pass is a true pass. Judge noise adds flakiness, which the flaky fraction stands in for.
- The distribution of flaky pass rates, Uniform(0.5, 0.95), is an assumption. The naive rate depends on E[p(1 − p)], which is symmetric around 0.5, so mostly-failing flaky cases would give similar results.
- These are simulated runs, not measurements of real agents. Once the executor (B1.7) and the demo agents run end to end, the same comparison can be repeated on recorded runs of the demo agents.

### Reproduce
```bash
uv run python scripts/measure_false_alarms.py            # 5,000 trials per cell (1,000 per calibration cell), seed 20260924
uv run python scripts/measure_false_alarms.py --trials 500 --grid-trials 200 --seed 1   # quicker, different draws
```
The script prints the tables above as Markdown. It runs offline in about 5 minutes and calls no LLM.
