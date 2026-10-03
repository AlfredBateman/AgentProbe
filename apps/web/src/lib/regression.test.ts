import { expect, test } from "vitest";
import { type RegressionReportDump, verdictSummary } from "./regression";

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

test("pValue never shows a tiny p as 0.0000", async () => {
  const { pValue } = await import("./format");
  expect(pValue(0.0125)).toBe("0.0125");
  expect(pValue(5.4e-6)).toBe("5.4e-6");
  expect(pValue(0)).toBe("0.0000");
  expect(pValue(1)).toBe("1.0000");
});
