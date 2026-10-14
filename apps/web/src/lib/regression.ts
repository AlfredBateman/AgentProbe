// The JSON shape of core's `RegressionReport` (agentprobe_core.stats.regression), as
// `GET /runs/compare` and `GET /runs/{id}/verdict` dump it (pydantic `TypeAdapter.dump_python`).
// `pass_rate` and `label` are core's computed fields: the label rule lives only in core.
import { pct, pValue } from "./format";

export type CaseSummaryDump = {
  passes: number;
  attempts: number;
  errors: number;
  mean_score: number | null;
  mean_latency_ms: number | null;
  cost_usd: number | null;
  pass_rate: number;
  label: "stable-pass" | "stable-fail" | "flaky";
};

export type MetricDeltaDump = { baseline: number; candidate: number; delta: number };

export type CaseComparisonDump = {
  case_id: string;
  baseline: CaseSummaryDump;
  candidate: CaseSummaryDump;
  pass_rate_delta: number;
  p_worse: number;
  p_worse_min: number;
  p_worse_threshold: number | null;
  p_better: number;
  p_better_min: number;
  p_better_threshold: number | null;
  regressed: boolean;
  improved: boolean;
  score_delta: number | null;
  latency_delta_ms: number | null;
  cost_per_attempt_delta_usd: number | null;
};

export type SuiteComparisonDump = {
  cases: number;
  baseline_pass_rate: number;
  candidate_pass_rate: number;
  pass_rate_delta: number;
  p_worse: number;
  p_better: number;
  exact: boolean;
  regressed: boolean;
  improved: boolean;
  score: MetricDeltaDump | null;
  latency_ms: MetricDeltaDump | null;
  cost_usd: MetricDeltaDump | null;
};

export type RegressionReportDump = {
  verdict: "regression" | "no_change" | "improvement";
  alpha: number;
  alpha_cases: number;
  alpha_suite: number;
  min_drop: number;
  suite: SuiteComparisonDump | null;
  cases: CaseComparisonDump[];
  regressed: string[];
  improved: string[];
  newly_failing: string[];
  newly_passing: string[];
  newly_flaky: string[];
  no_longer_flaky: string[];
  added: string[];
  removed: string[];
};

const signedPct = (x: number) => `${x >= 0 ? "+" : ""}${pct(x)}`;

/** A pass-rate difference in percentage points: the verdict's effect size. */
export const points = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(x * 100).toFixed(1)} pts`;

export type VerdictLine = {
  verdict: RegressionReportDump["verdict"];
  /** The verdict's word, as the labels spell it. */
  word: string;
  /** What decided it, from the report's own values: the case, its p and the threshold it met. */
  detail: string;
};

const WORD = { regression: "Regression", improvement: "Improvement", no_change: "No change" } as const;

/**
 * The verdict as one sentence's worth of numbers (`Regression: refund-flow, p=0.0040, corrected
 * threshold=0.0100`). Every figure is the report's. The per-case family has corrected thresholds,
 * not adjusted p-values (ADR 0014), so the sentence says "corrected threshold" and never "corrected p".
 */
export function verdictLine(r: RegressionReportDump): VerdictLine {
  const word = WORD[r.verdict];
  const n = r.suite?.cases ?? r.cases.length;
  const cases = `${n} shared ${n === 1 ? "case" : "cases"}`;

  if (r.verdict === "no_change") {
    if (r.cases.length === 0) return { verdict: r.verdict, word, detail: "no shared cases to compare" };
    const lowest = r.cases.reduce((a, b) => (b.p_worse < a.p_worse ? b : a));
    return { verdict: r.verdict, word, detail: `${cases}, none significant; lowest p=${pValue(lowest.p_worse)} (${lowest.case_id})` };
  }

  const better = r.verdict === "improvement";
  const flagged = r.cases
    .filter((c) => (better ? c.improved : c.regressed))
    .toSorted((a, b) => (better ? a.p_better - b.p_better : a.p_worse - b.p_worse));
  const top = flagged[0];
  if (top) {
    const p = better ? top.p_better : top.p_worse;
    const threshold = better ? top.p_better_threshold : top.p_worse_threshold;
    const parts = [top.case_id, `p=${pValue(p)}`];
    if (threshold !== null) parts.push(`corrected threshold=${pValue(threshold)}`);
    if (flagged.length > 1) parts.push(`+${flagged.length - 1} more ${flagged.length === 2 ? "case" : "cases"}`);
    return { verdict: r.verdict, word, detail: parts.join(", ") };
  }

  // No single case fired: the suite-level paired test did.
  const s = r.suite;
  const p = s ? (better ? s.p_better : s.p_worse) : null;
  return {
    verdict: r.verdict,
    word,
    detail: s && p !== null ? `suite pass rate ${points(s.pass_rate_delta)}, p=${pValue(p)} vs α_suite=${r.alpha_suite}` : cases,
  };
}

/** The verdict's own statistics in plain language: which channel fired, its significance, effect size and N. */
export function verdictSummary(r: RegressionReportDump): string {
  const n = r.suite?.cases ?? r.cases.length;
  if (r.verdict === "no_change") {
    return `No statistically significant change across ${n} shared ${n === 1 ? "case" : "cases"} (α = ${r.alpha}, min drop ${pct(r.min_drop)}).`;
  }
  const worse = r.verdict === "regression";
  const flagged = worse ? r.regressed : r.improved;
  const parts: string[] = [];
  if (flagged.length > 0) {
    parts.push(
      `${flagged.length} ${flagged.length === 1 ? "case" : "cases"} (${flagged.join(", ")}) ${worse ? "dropped" : "rose"} significantly ` +
        `(one-sided Fisher exact, Tarone–Holm step-down, α_cases = ${r.alpha_cases}).`,
    );
  }
  const suiteFlagged = r.suite && (worse ? r.suite.regressed : r.suite.improved);
  if (suiteFlagged && r.suite) {
    const p = worse ? r.suite.p_worse : r.suite.p_better;
    parts.push(
      `The suite pass rate moved ${signedPct(r.suite.pass_rate_delta)} across ${n} shared cases ` +
        `(p = ${pValue(p)} vs α_suite = ${r.alpha_suite}, paired sign-flip test${r.suite.exact ? "" : ", Monte Carlo"}).`,
    );
  }
  return parts.join(" ");
}

export { signedPct };
