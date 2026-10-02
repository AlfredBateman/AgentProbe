import { describe, expect, it } from "vitest";
import { type Baseline, baselineBranches, defaultSuite, isEmpty, type RunRow, suiteBaseline, trendPoints } from "./trends";

const run = (over: Partial<RunRow>): RunRow => ({
  id: "r",
  suite_id: "s1",
  suite_name: "smoke",
  agent_id: "a",
  agent_name: "support-v1",
  status: "completed",
  branch: null,
  mock_mode: true,
  pass_rate: 0.9,
  ci_lower: 0.8,
  ci_upper: 1,
  total_cost: null,
  judge_cost_usd: 0,
  total_tokens: null,
  mean_latency_ms: 12,
  created_at: "2026-10-01T10:00:00Z",
  finished_at: null,
  ...over,
});

const baseline = (over: Partial<Baseline>): Baseline =>
  ({ branch: "main", suite_id: "s1", agent_id: "a", agent_name: null, run_id: "r", run: {}, ...over }) as Baseline;

describe("trendPoints", () => {
  it("keeps one suite's completed runs, oldest first", () => {
    const runs = [
      run({ id: "new", created_at: "2026-10-03T00:00:00Z" }),
      run({ id: "other-suite", suite_id: "s2" }),
      run({ id: "failed", status: "failed" }),
      run({ id: "running", status: "running" }),
      run({ id: "old", created_at: "2026-09-01T00:00:00Z" }),
    ];
    expect(trendPoints(runs, "s1").map((p) => p.id)).toEqual(["old", "new"]);
  });

  it("gives the CI as a range, or null when the run has none", () => {
    const [withCi, without] = trendPoints(
      [run({ id: "a" }), run({ id: "b", created_at: "2026-10-02T00:00:00Z", ci_lower: null })],
      "s1",
    );
    expect(withCi.band).toEqual([0.8, 1]);
    expect(without.band).toBeNull();
  });
});

describe("defaultSuite", () => {
  it("is the newest run's suite, or null without runs", () => {
    expect(defaultSuite([run({ suite_id: "s2" }), run({})])).toBe("s2");
    expect(defaultSuite([])).toBeNull();
  });
});

describe("suiteBaseline", () => {
  it("prefers main's baseline for the suite", () => {
    const list = [baseline({ branch: "release", run_id: "x" }), baseline({ run_id: "y" }), baseline({ suite_id: "s2", run_id: "z" })];
    expect(suiteBaseline(list, "s1")?.run_id).toBe("y");
    expect(suiteBaseline(list.slice(0, 1), "s1")?.run_id).toBe("x");
    expect(suiteBaseline(list, "s3")).toBeNull();
  });
});

describe("baselineBranches", () => {
  it("lists every branch a run is the baseline of", () => {
    const map = baselineBranches([baseline({ run_id: "y" }), baseline({ branch: "release", run_id: "y" }), baseline({ run_id: "z" })]);
    expect(map.get("y")).toEqual(["main", "release"]);
    expect(map.get("z")).toEqual(["main"]);
    expect(map.get("nope")).toBeUndefined();
  });
});

describe("isEmpty", () => {
  it("is true only when every point lacks every key", () => {
    const points = trendPoints([run({ total_cost: null, judge_cost_usd: null })], "s1");
    expect(isEmpty(points, "cost", "judge")).toBe(true);
    expect(isEmpty(points, "latency")).toBe(false);
    expect(isEmpty([], "pass")).toBe(true);
  });
});
