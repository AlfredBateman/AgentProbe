import { expect, test } from "vitest";
import { type RegressionReportDump, verdictLine, verdictSummary } from "./regression";

const summary = (passes: number, attempts: number, label: "stable-pass" | "stable-fail" | "flaky") => ({
  passes,
  attempts,
  errors: 0,
  mean_score: null,
  mean_latency_ms: null,
  cost_usd: null,
  pass_rate: passes / attempts,
  label,
});

function report(overrides: Partial<RegressionReportDump>): RegressionReportDump {
  return {
    verdict: "no_change",
    alpha: 0.05,
    alpha_cases: 0.025,
    alpha_suite: 0.025,
    min_drop: 0.05,
    suite: null,
    cases: [],
    regressed: [],
    improved: [],
    newly_failing: [],
    newly_passing: [],
    newly_flaky: [],
    no_longer_flaky: [],
    added: [],
    removed: [],
    ...overrides,
  };
}

test("no_change names alpha and min_drop, not a case", () => {
  const text = verdictSummary(report({ suite: { cases: 9, baseline_pass_rate: 1, candidate_pass_rate: 1, pass_rate_delta: 0, p_worse: 1, p_better: 1, exact: true, regressed: false, improved: false, score: null, latency_ms: null, cost_usd: null } }));
  expect(text).toContain("No statistically significant change across 9 shared cases");
  expect(text).toContain("α = 0.05");
  expect(text).not.toMatch(/case \(/);
});

test("a flagged case names itself, its test and its alpha share", () => {
  const text = verdictSummary(
    report({
      verdict: "regression",
      regressed: ["refund-outside-window"],
      cases: [
        {
          case_id: "refund-outside-window",
          baseline: summary(5, 5, "stable-pass"),
          candidate: summary(0, 5, "stable-fail"),
          pass_rate_delta: -1,
          p_worse: 0.004,
          p_worse_min: 0.004,
          p_worse_threshold: 0.025,
          p_better: 1,
          p_better_min: 1,
          p_better_threshold: null,
          regressed: true,
          improved: false,
          score_delta: null,
          latency_delta_ms: null,
          cost_per_attempt_delta_usd: null,
        },
      ],
    }),
  );
  expect(text).toContain("1 case (refund-outside-window) dropped significantly");
  expect(text).toContain("α_cases = 0.025");
});

test("a suite-level regression names its p-value, delta and N, not a case", () => {
  const text = verdictSummary(
    report({
      verdict: "regression",
      suite: {
        cases: 30,
        baseline_pass_rate: 0.9,
        candidate_pass_rate: 0.7,
        pass_rate_delta: -0.2,
        p_worse: 0.001,
        p_better: 1,
        exact: false,
        regressed: true,
        improved: false,
        score: null,
        latency_ms: null,
        cost_usd: null,
      },
    }),
  );
  expect(text).toContain("suite pass rate moved -20.0% across 30 shared cases");
  expect(text).toContain("p = 0.0010 vs α_suite = 0.025");
  expect(text).toContain("Monte Carlo");
});

const flaggedCase = (id: string, over: Partial<RegressionReportDump["cases"][number]> = {}): RegressionReportDump["cases"][number] => ({
  case_id: id,
  baseline: summary(5, 5, "stable-pass"),
  candidate: summary(0, 5, "stable-fail"),
  pass_rate_delta: -1,
  p_worse: 0.004,
  p_worse_min: 0.004,
  p_worse_threshold: 0.0125,
  p_better: 1,
  p_better_min: 1,
  p_better_threshold: null,
  regressed: true,
  improved: false,
  score_delta: null,
  latency_delta_ms: null,
  cost_per_attempt_delta_usd: null,
  ...over,
});

const suiteOf = (over: Partial<NonNullable<RegressionReportDump["suite"]>> = {}): NonNullable<RegressionReportDump["suite"]> => ({
  cases: 8,
  baseline_pass_rate: 0.9,
  candidate_pass_rate: 0.7,
  pass_rate_delta: -0.2,
  p_worse: 0.0123,
  p_better: 1,
  exact: true,
  regressed: false,
  improved: false,
  score: null,
  latency_ms: null,
  cost_usd: null,
  ...over,
});

test("verdictLine names the most significant flagged case with its p and its corrected threshold", () => {
  const line = verdictLine(
    report({
      verdict: "regression",
      regressed: ["refund-flow", "tone"],
      cases: [flaggedCase("tone", { p_worse: 0.02, p_worse_threshold: 0.025 }), flaggedCase("refund-flow")],
    }),
  );
  expect(line).toEqual({
    verdict: "regression",
    word: "Regression",
    detail: "refund-flow, p=0.0040, corrected threshold=0.0125, +1 more case",
  });
});

test("verdictLine never calls a threshold a corrected p-value, and reads a tiny p as scientific", () => {
  const line = verdictLine(report({ verdict: "regression", cases: [flaggedCase("c", { p_worse: 5.4e-6 })] }));
  expect(line.detail).toBe("c, p=5.4e-6, corrected threshold=0.0125");
  expect(line.detail).not.toMatch(/corrected p\b/);
});

test("an improvement reads the better-direction p and threshold", () => {
  const line = verdictLine(
    report({
      verdict: "improvement",
      cases: [flaggedCase("c", { regressed: false, improved: true, p_better: 0.01, p_better_threshold: 0.02, p_worse: 1 })],
    }),
  );
  expect(line).toMatchObject({ word: "Improvement", detail: "c, p=0.0100, corrected threshold=0.0200" });
});

test("a suite-level regression with no flagged case states the paired test", () => {
  const line = verdictLine(report({ verdict: "regression", suite: suiteOf({ regressed: true }), cases: [flaggedCase("c", { regressed: false })] }));
  expect(line.detail).toBe("suite pass rate −20.0 pts, p=0.0123 vs α_suite=0.025");
});

test("no change states how many cases were compared and the lowest p, not a threshold", () => {
  const line = verdictLine(
    report({ suite: suiteOf(), cases: [flaggedCase("a", { regressed: false, p_worse: 0.3 }), flaggedCase("b", { regressed: false, p_worse: 0.08 })] }),
  );
  expect(line).toEqual({ verdict: "no_change", word: "No change", detail: "8 shared cases, none significant; lowest p=0.0800 (b)" });
  expect(verdictLine(report({})).detail).toBe("no shared cases to compare");
});

test("pValue never shows a tiny p as 0.0000", async () => {
  const { pValue } = await import("./format");
  expect(pValue(0.0125)).toBe("0.0125");
  expect(pValue(5.4e-6)).toBe("5.4e-6");
  expect(pValue(0)).toBe("0.0000");
  expect(pValue(1)).toBe("1.0000");
});
