# 0006: Regression statistics methodology

Status: accepted (2026-09-25)

## Context
SPEC.md §4.6–4.7 requires that "a regression is flagged only when the drop is statistically meaningful" but specifies no method. Given non-deterministic agents and a small `runs_per_case` (typically 3–10), the method has to handle: per-case pass rates that are really small binomial samples, a suite-level pass rate that's a mean over cases (not over pooled attempts, since attempts within a case are correlated, not independent), and users who want to compare two runs (baseline vs. candidate) without hand-picking a statistical test.

## Decision
- **Attempt outcome.** An attempt passes when every expectation on the case passes. A timeout or adapter failure that survives retries is `error`, counted as not-passed, and shown separately from a judged failure.
- **Case labels.** Over `n` attempts with `k` passes: `stable-pass` when `k = n`, `stable-fail` when `k = 0`, `flaky` otherwise.
- **Suite pass rate.** The mean of per-case pass rates (not pooled attempts). Its 95% confidence interval comes from a seeded case-level cluster bootstrap — resampling cases, not individual attempts — because Wilson or a normal approximation on pooled attempts would be artificially narrow given the within-case correlation.
- **Per-case regression** (baseline vs. candidate on the same case): a one-sided Fisher exact test on the 2×2 pass/fail table, Holm-corrected across all cases in the suite to control the family-wise error rate.
- **Suite-level regression**: a one-sided paired sign-flip permutation test on the per-case pass-rate deltas — exact enumeration up to 20 cases, otherwise 10,000 seeded Monte Carlo draws.
- **Flagging rule.** A regression is only reported when the test is significant **and** the pass-rate drop is at least `min_drop`. This avoids flagging a significant-but-trivial 1% drop.
- **Defaults.** `alpha = 0.05`, `min_drop = 0.05`, permutation draws `= 10000`, bootstrap resamples `= 10000`. **All four are configurable**, both in the suite YAML (a top-level `statistics:` block) and as CLI flags (e.g. `--alpha`, `--min-drop`) on `agentprobe run` / `agentprobe compare` — nothing here is hardcoded past the default.
- **`--fail-under`.** Compares against the point estimate of the suite pass rate, not the confidence interval's lower bound.
- **Implementation.** Python standard library only: `math.comb` for the exact Fisher/permutation paths, `random.Random(seed)` for the Monte Carlo fallback and the bootstrap. No SciPy/NumPy dependency in `packages/core`.

### Documented limitation
At `runs_per_case = 5`, a single case only reaches `p < 0.05` on a large drop (e.g., 5/5 → 1/5); smaller drops need either more runs per case or accumulate evidence at the suite level across many cases. This is stated in the CLI's `--help` text for `compare` and in the statistics section of the user docs, not left as a silent caveat.

## Consequences
- `packages/core`'s statistics module has no third-party numerical dependency, keeping `pnpm check` fast and the package's dependency surface small.
- Suite-level and case-level regression use different tests deliberately (paired permutation vs. Fisher+Holm) because they answer different questions — "did this specific case get worse" vs. "did the suite as a whole get worse" — and conflating them into one test would either miss localized regressions or over-flag on noisy suites.
- Configurability means the statistics module's public API takes these parameters explicitly (no hidden module-level constants), which the YAML schema (B1.1) and CLI argument parsing (D1.1, D2.1) both need to plumb through.
