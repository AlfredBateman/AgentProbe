import type { components } from "./api/schema";
import type { StreamAttempt } from "./use-run-stream";

type Result = components["schemas"]["ResultOut"];
type Summary = components["schemas"]["CaseSummaryOut"];

/** An attempt as the run page knows it: complete from GET /runs/{id}/results, or partial from the stream. */
export type Attempt = Pick<Result, "id" | "case" | "attempt" | "status" | "score" | "latency_ms" | "cost"> &
  Partial<Pick<Result, "attack_category">>;

export type Label = "stable-pass" | "stable-fail" | "flaky";

export type CaseRow = {
  case: string;
  attackCategory: string | null;
  /** Null until the run is summarized: the label is core's call, not the page's. */
  label: Label | null;
  attempts: Attempt[];
  /** Attempts finished: the summary's count once there is one. */
  done: number;
  passes: number;
  errors: number;
  meanScore: number | null;
  consistency: number | null;
  meanLatencyMs: number | null;
  /** Null unless every attempt's cost is known, as core reports it. */
  totalCost: number | null;
};

export const attemptKey = (a: { case: string; attempt: number }) => `${a.case}#${a.attempt}`;

export const fromStream = (a: StreamAttempt): Attempt => ({
  id: a.result_id,
  case: a.case,
  attempt: a.attempt,
  status: a.status,
  score: a.score,
  latency_ms: a.latency_ms,
  cost: a.cost_usd,
});

/** Fetched attempts are complete, so they replace streamed ones; nothing already known is dropped. */
export function mergeAttempts(known: ReadonlyMap<string, Attempt>, incoming: Attempt[]): Map<string, Attempt> {
  const next = new Map(known);
  for (const a of incoming) next.set(attemptKey(a), { ...next.get(attemptKey(a)), ...a });
  return next;
}

function mean(values: (number | null)[]): number | null {
  const known = values.filter((v): v is number => v !== null);
  return known.length ? known.reduce((s, v) => s + v, 0) / known.length : null;
}

/** One row per case: the persisted summary once the run has one, otherwise live aggregates. */
export function caseRows(attempts: Iterable<Attempt>, summaries: Summary[]): CaseRow[] {
  const byCase = new Map<string, Attempt[]>();
  for (const a of attempts) byCase.set(a.case, [...(byCase.get(a.case) ?? []), a]);
  const summaryOf = new Map(summaries.map((s) => [s.case, s]));
  const cases = new Set([...byCase.keys(), ...summaryOf.keys()]);

  return [...cases].sort().map((key) => {
    const list = (byCase.get(key) ?? []).toSorted((a, b) => a.attempt - b.attempt);
    const s = summaryOf.get(key);
    if (s) {
      return {
        case: key,
        attackCategory: s.attack_category,
        label: s.label as Label,
        attempts: list,
        done: s.attempts,
        passes: s.passes,
        errors: s.errors,
        meanScore: s.mean_score,
        consistency: s.consistency_score,
        meanLatencyMs: s.mean_latency_ms,
        totalCost: s.total_cost,
      };
    }
    const costs = list.map((a) => a.cost);
    return {
      case: key,
      attackCategory: list.find((a) => a.attack_category)?.attack_category ?? null,
      label: null,
      attempts: list,
      done: list.length,
      passes: list.filter((a) => a.status === "passed").length,
      errors: list.filter((a) => a.status === "error").length,
      meanScore: mean(list.map((a) => a.score)),
      consistency: null,
      meanLatencyMs: mean(list.map((a) => a.latency_ms)),
      totalCost: costs.length && costs.every((c) => c !== null) ? costs.reduce((t, c) => t! + c!, 0) : null,
    };
  });
}

export type Filters = { q: string; status: string; label: string; category: string };
export const NO_FILTERS: Filters = { q: "", status: "", label: "", category: "" };

/** `status` keeps cases with at least one attempt of that status. */
export function filterRows(rows: CaseRow[], f: Filters): CaseRow[] {
  const q = f.q.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (!q || r.case.toLowerCase().includes(q)) &&
      (!f.status || r.attempts.some((a) => a.status === f.status)) &&
      (!f.label || r.label === f.label) &&
      (!f.category || r.attackCategory === f.category),
  );
}
