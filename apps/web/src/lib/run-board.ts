// The run board: one cell per case, in the suite's order, each in one state. A cell's final word
// is core's label (from the run's summaries); before the summaries exist it is read from the
// attempts seen so far, and says so by being "running" until the case has all of them.
import type { Status } from "@/components/ui/status";
import type { Attempt, CaseRow } from "./run-cases";

export type CellState = "queued" | "running" | "pass" | "fail" | "flaky" | "error" | "not-run";

export type Cell = {
  case: string;
  state: CellState;
  /** One slot per planned attempt, by attempt number: null until it has finished. */
  slots: (Attempt["status"] | null)[];
  passes: number;
  done: number;
  /** The attempt to open: the first failing one, else the first. */
  resultId: string | null;
};

export const CELL_TEXT: Record<CellState, string> = {
  queued: "Queued",
  running: "Running",
  pass: "Pass",
  fail: "Fail",
  flaky: "Flaky",
  error: "Error",
  "not-run": "Not run",
};

/** The DESIGN.md status mark for each state ("not run" borrows the queued mark: it never started). */
export const CELL_MARK: Record<CellState, Status> = {
  queued: "queued",
  running: "running",
  pass: "pass",
  fail: "fail",
  flaky: "flaky",
  error: "error",
  "not-run": "queued",
};

function state(row: CaseRow | undefined, runsPerCase: number, live: boolean): CellState {
  if (!row || row.done === 0) return live ? "queued" : "not-run";
  const allErrors = row.errors === row.done;
  if (row.label === "stable-pass") return "pass";
  if (row.label === "flaky") return "flaky";
  if (row.label === "stable-fail") return allErrors ? "error" : "fail";
  if (live && row.done < runsPerCase) return "running";
  if (row.passes === row.done) return "pass";
  if (row.passes === 0) return allErrors ? "error" : "fail";
  return "flaky";
}

/**
 * `caseIds` is the suite version's cases in YAML order (so queued cases have a cell before their
 * first attempt); a case seen only in the attempts (an ingested run) is added after them.
 */
export function boardCells(caseIds: string[], rows: CaseRow[], runsPerCase: number, live: boolean): Cell[] {
  const byCase = new Map(rows.map((r) => [r.case, r]));
  const order = [...new Set([...caseIds, ...rows.map((r) => r.case)])];
  return order.map((id) => {
    const row = byCase.get(id);
    const attempts = row?.attempts ?? [];
    const slots: Cell["slots"] = Array.from({ length: Math.max(runsPerCase, attempts.length) }, () => null);
    for (const a of attempts) if (a.attempt < slots.length) slots[a.attempt] = a.status;
    const failing = attempts.find((a) => a.status !== "passed");
    return {
      case: id,
      state: state(row, runsPerCase, live),
      slots,
      passes: row?.passes ?? 0,
      done: row?.done ?? 0,
      resultId: (failing ?? attempts[0])?.id ?? null,
    };
  });
}

/** How many cells are in each state, in the legend's order. */
export function tally(cells: Cell[]): [CellState, number][] {
  const states: CellState[] = ["queued", "running", "pass", "fail", "flaky", "error", "not-run"];
  return states.map((s) => [s, cells.filter((c) => c.state === s).length]);
}

/** Filled segments of an `n`-segment bar: none until an attempt is done, all only when every one is. */
export function segments(done: number, total: number, n: number): number {
  if (total <= 0 || done <= 0) return 0;
  if (done >= total) return n;
  return Math.min(n - 1, Math.max(1, Math.floor((done / total) * n)));
}
