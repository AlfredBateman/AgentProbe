// The JSON shape of core's `RegressionReport` (agentprobe_core.stats.regression), as
// `GET /runs/compare` and `GET /runs/{id}/verdict` dump it (pydantic `TypeAdapter.dump_python`).
// `pass_rate` and `label` are core's computed fields: the label rule lives only in core.
import { pct } from "./format";

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
        `(p = ${p.toFixed(4)} vs α_suite = ${r.alpha_suite}, paired sign-flip test${r.suite.exact ? "" : ", Monte Carlo"}).`,
    );
  }
  return parts.join(" ");
}

export { signedPct };
