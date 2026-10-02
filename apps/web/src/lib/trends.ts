// The project overview's trend data (E2): one suite's completed runs, oldest first.
import type { components } from "@/lib/api/schema";

export type RunRow = components["schemas"]["RunListOut"];
export type Baseline = components["schemas"]["BaselineOut"];

export type TrendPoint = {
  id: string;
  at: string;
  pass: number | null;
  /** The 95% CI as [lower, upper], the shape a Recharts range area takes. */
  band: [number, number] | null;
  cost: number | null;
  judge: number | null;
  latency: number | null;
};

/** Completed runs of `suiteId`, oldest first. Failed and cancelled runs have no statistics. */
export function trendPoints(runs: readonly RunRow[], suiteId: string): TrendPoint[] {
  return runs
    .filter((r) => r.suite_id === suiteId && r.status === "completed")
    .toSorted((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
    .map((r) => ({
      id: r.id,
      at: r.created_at,
      pass: r.pass_rate,
      band: r.ci_lower != null && r.ci_upper != null ? [r.ci_lower, r.ci_upper] : null,
      cost: r.total_cost,
      judge: r.judge_cost_usd,
      latency: r.mean_latency_ms,
    }));
}

/** The suite the overview opens on: the one with the newest run (`runs` is newest first). */
export const defaultSuite = (runs: readonly RunRow[]): string | null => runs[0]?.suite_id ?? null;

/** The baseline drawn on a suite's pass-rate trend: `main`'s if there is one, else any. */
export function suiteBaseline(baselines: readonly Baseline[], suiteId: string): Baseline | null {
  const own = baselines.filter((b) => b.suite_id === suiteId);
  return own.find((b) => b.branch === "main") ?? own[0] ?? null;
}

/** Run id -> the branches it is the baseline of, for the runs table's indicator. */
export function baselineBranches(baselines: readonly Baseline[]): ReadonlyMap<string, string[]> {
  const byRun = new Map<string, string[]>();
  for (const b of baselines) byRun.set(b.run_id, [...(byRun.get(b.run_id) ?? []), b.branch]);
  return byRun;
}

/** True when a series has nothing to draw, so the chart shows a note instead of empty axes. */
export const isEmpty = (points: readonly TrendPoint[], ...keys: ("pass" | "cost" | "judge" | "latency")[]) =>
  points.every((p) => keys.every((k) => p[k] == null));
