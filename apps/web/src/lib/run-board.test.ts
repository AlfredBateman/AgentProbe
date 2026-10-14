import { expect, test } from "vitest";
import { boardCells, segments, tally } from "./run-board";
import { type Attempt, caseRows } from "./run-cases";

const attempt = (c: string, n: number, status: string): Attempt => ({
  id: `${c}-${n}`,
  case: c,
  attempt: n,
  status,
  score: null,
  latency_ms: null,
  cost: null,
});

const summary = (c: string, label: string, passes: number, attempts: number, errors = 0) => ({
  case: c,
  label,
  passes,
  attempts,
  errors,
  pass_rate: passes / attempts,
  attack_category: null,
  mean_score: null,
  consistency_score: null,
  mean_latency_ms: null,
  total_cost: null,
});

test("a live board: every suite case has a cell in YAML order, queued until its first attempt", () => {
  const rows = caseRows([attempt("b", 0, "passed"), attempt("b", 1, "failed")], []);
  const cells = boardCells(["c", "b", "a"], rows, 3, true);
  expect(cells.map((c) => [c.case, c.state])).toEqual([
    ["c", "queued"],
    ["b", "running"],
    ["a", "queued"],
  ]);
  expect(cells[1].slots).toEqual(["passed", "failed", null]);
  expect(cells[1].resultId).toBe("b-1"); // the failing attempt opens first
  expect(cells[0].resultId).toBeNull();
});

test("before the summaries, a finished case is read from its attempts", () => {
  const attempts = [
    ...[0, 1].map((n) => attempt("pass", n, "passed")),
    ...[0, 1].map((n) => attempt("fail", n, "failed")),
    attempt("flaky", 0, "passed"),
    attempt("flaky", 1, "failed"),
    ...[0, 1].map((n) => attempt("err", n, "error")),
  ];
  const cells = boardCells([], caseRows(attempts, []), 2, true);
  expect(Object.fromEntries(cells.map((c) => [c.case, c.state]))).toEqual({ err: "error", fail: "fail", flaky: "flaky", pass: "pass" });
});

test("core's label has the last word once the run is summarized", () => {
  // Attempts say all passed, but the summary is what core decided.
  const attempts = [attempt("a", 0, "passed"), attempt("a", 1, "passed"), attempt("e", 0, "error")];
  const rows = caseRows(attempts, [summary("a", "flaky", 1, 2), summary("e", "stable-fail", 0, 1, 1), summary("f", "stable-fail", 0, 2)]);
  const cells = boardCells(["a", "e", "f", "never"], rows, 2, false);
  expect(cells.map((c) => c.state)).toEqual(["flaky", "error", "fail", "not-run"]);
  expect(tally(cells).filter(([, n]) => n)).toEqual([
    ["fail", 1],
    ["flaky", 1],
    ["error", 1],
    ["not-run", 1],
  ]);
});

test("an ingested run's cases come from its attempts when the suite has no such case", () => {
  const cells = boardCells(["a"], caseRows([attempt("z", 0, "passed")], []), 1, false);
  expect(cells.map((c) => c.case)).toEqual(["a", "z"]);
});

test("segments: empty at zero, full only at the end, at least one once anything is done", () => {
  expect(segments(0, 45, 40)).toBe(0);
  expect(segments(1, 45, 40)).toBe(1);
  expect(segments(22, 45, 40)).toBe(19);
  expect(segments(44, 45, 40)).toBe(39);
  expect(segments(45, 45, 40)).toBe(40);
  expect(segments(3, 0, 40)).toBe(0);
});
