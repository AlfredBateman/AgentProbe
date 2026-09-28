import { expect, test } from "vitest";
import { type Attempt, attemptKey, caseRows, filterRows, fromStream, mergeAttempts, NO_FILTERS } from "./run-cases";

const attempt = (c: string, n: number, over: Partial<Attempt> = {}): Attempt => ({
  id: `${c}-${n}`,
  case: c,
  attempt: n,
  status: "passed",
  score: 1,
  latency_ms: 100,
  cost: 0.01,
  ...over,
});

test("a fetch fills in streamed attempts and never drops ones it didn't see", () => {
  const streamed = (n: number) =>
    fromStream({ case: "a", attempt: n, status: "failed", result_id: `a-${n}`, latency_ms: 50, cost_usd: null, score: 0, done: n + 1, total: 4 });
  let known = mergeAttempts(new Map(), [streamed(0), streamed(1)]);
  // The fetch started before a-1 was saved: it only knows a-0, now with its attack category.
  known = mergeAttempts(known, [attempt("a", 0, { status: "failed", score: 0, attack_category: "jailbreak" })]);
  expect([...known.keys()]).toEqual(["a#0", "a#1"]);
  expect(known.get("a#0")).toMatchObject({ status: "failed", attack_category: "jailbreak", cost: 0.01 });
  expect(known.get("a#1")).toMatchObject({ id: "a-1", cost: null });
  expect(attemptKey({ case: "a", attempt: 1 })).toBe("a#1");
});

test("live rows aggregate their attempts; cost is unknown if any attempt's is", () => {
  const rows = caseRows(
    [
      attempt("b", 1, { status: "failed", score: 0, latency_ms: 300 }),
      attempt("b", 0),
      attempt("a", 0, { cost: null }),
      attempt("b", 2, { status: "error", score: null, latency_ms: null }),
    ],
    [],
  );
  expect(rows.map((r) => r.case)).toEqual(["a", "b"]);
  const b = rows[1];
  expect(b.attempts.map((a) => a.attempt)).toEqual([0, 1, 2]);
  expect([b.done, b.passes, b.errors, b.label, b.consistency]).toEqual([3, 1, 1, null, null]);
  expect(b.meanScore).toBe(0.5); // the error's null score is left out, not counted as 0
  expect(b.meanLatencyMs).toBe(200);
  expect(b.totalCost).toBeCloseTo(0.03);
  expect(rows[0].totalCost).toBeNull();
});

test("a persisted summary wins over live aggregates, and summary-only cases still show", () => {
  const summary = {
    case: "b",
    attack_category: "prompt_injection",
    label: "flaky",
    attempts: 5,
    passes: 4,
    errors: 0,
    pass_rate: 0.8,
    mean_score: 0.8,
    consistency_score: 0.9,
    mean_latency_ms: 120,
    total_cost: null,
  };
  const rows = caseRows([attempt("b", 0)], [summary, { ...summary, case: "c", label: "stable-pass" }]);
  expect(rows.map((r) => [r.case, r.label, r.done, r.passes, r.consistency, r.attackCategory])).toEqual([
    ["b", "flaky", 5, 4, 0.9, "prompt_injection"],
    ["c", "stable-pass", 5, 4, 0.9, "prompt_injection"],
  ]);
  expect(rows[0].attempts).toHaveLength(1);
});

test("filters combine: search, attempt status, label and attack category", () => {
  const rows = caseRows(
    [
      attempt("greeting", 0),
      attempt("order-status", 0, { status: "failed" }),
      attempt("api-key-leak", 0, { attack_category: "data_exfiltration" }),
    ],
    [],
  );
  const cases = (f: Partial<typeof NO_FILTERS>) => filterRows(rows, { ...NO_FILTERS, ...f }).map((r) => r.case);
  expect(cases({})).toEqual(["api-key-leak", "greeting", "order-status"]);
  expect(cases({ q: " ORDER " })).toEqual(["order-status"]);
  expect(cases({ status: "failed" })).toEqual(["order-status"]);
  expect(cases({ category: "data_exfiltration" })).toEqual(["api-key-leak"]);
  expect(cases({ label: "flaky" })).toEqual([]); // no labels until the run is summarized
  expect(cases({ q: "greet", status: "failed" })).toEqual([]);
});
