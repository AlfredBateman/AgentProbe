import { render, screen, within } from "@testing-library/react";
import gsap from "gsap";
import { afterEach, describe, expect, test } from "vitest";
import type { components } from "@/lib/api/schema";
import { REDUCE_ATTR } from "@/lib/motion/core";
import type { RegressionReportDump } from "@/lib/regression";
import { boardCells, type Cell } from "@/lib/run-board";
import { type Attempt, caseRows } from "@/lib/run-cases";
import { CaseBoard, ProgressStrip } from "./board";
import { FailureClusters } from "./failure-clusters";
import { CaseTests, points, StatsPanel } from "./stats-panel";

type Run = components["schemas"]["RunDetailOut"];

function setReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("no-preference") ? !reduce : reduce,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

afterEach(() => {
  setReducedMotion(true);
  document.documentElement.removeAttribute(REDUCE_ATTR);
  gsap.globalTimeline.clear();
});

const attempt = (c: string, n: number, status: string): Attempt => ({ id: `${c}-${n}`, case: c, attempt: n, status, score: null, latency_ms: null, cost: null });
const cells = (attempts: Attempt[], live = true): Cell[] => boardCells(["greeting", "order-status"], caseRows(attempts, []), 2, live);

describe("case board", () => {
  test("each cell says its state in words, with its mark, and opens its failing attempt", () => {
    render(<CaseBoard cells={cells([attempt("order-status", 0, "failed")])} projectId="p" runId="r" />);
    const board = screen.getByRole("list", { name: "Case board" });
    const [greeting, order] = within(board).getAllByRole("listitem");
    expect(greeting.dataset.state).toBe("queued");
    expect(within(greeting).getByRole("group", { name: "greeting: Queued" })).toBeTruthy();
    const link = within(order).getByRole("link", { name: "order-status: Running, 0 of 1 attempts passed" });
    expect(link.getAttribute("href")).toBe("/projects/p/runs/r/results/order-status-0");
    expect(within(screen.getByRole("list", { name: "Cases by state" })).getByText("Queued").textContent).toContain("1");
  });

  function flashTweens(rerender: (ui: React.ReactElement) => void, container: HTMLElement) {
    const before = [...container.querySelectorAll("[data-flash]")].map((el) => gsap.getTweensOf(el).length);
    rerender(<CaseBoard cells={cells([attempt("greeting", 0, "passed"), attempt("greeting", 1, "passed")])} projectId="p" runId="r" />);
    const after = [...container.querySelectorAll("[data-flash]")].map((el) => gsap.getTweensOf(el).length);
    return { before, after };
  }

  test("a state change flashes that cell once; loading a board flashes nothing", () => {
    setReducedMotion(false);
    const { rerender, container } = render(<CaseBoard cells={cells([])} projectId="p" runId="r" />);
    const { before, after } = flashTweens(rerender, container);
    expect(before).toEqual([0, 0]);
    expect(after).toEqual([1, 0]); // greeting went queued -> pass; order-status stayed queued
  });

  test("under reduced motion, or the dev switch, nothing flashes", () => {
    setReducedMotion(true);
    let r = render(<CaseBoard cells={cells([])} projectId="p" runId="r" />);
    expect(flashTweens(r.rerender, r.container).after).toEqual([0, 0]);
    r.unmount();

    setReducedMotion(false);
    document.documentElement.setAttribute(REDUCE_ATTR, "");
    r = render(<CaseBoard cells={cells([])} projectId="p" runId="r" />);
    expect(flashTweens(r.rerender, r.container).after).toEqual([0, 0]);
  });
});

test("the progress strip is a labelled progressbar of 40 segments", () => {
  render(
    <ProgressStrip
      status="running"
      done={9}
      total={45}
      startedAt={null}
      attempts={[attempt("a", 0, "passed"), attempt("a", 1, "failed")]}
      connection="live"
    />,
  );
  const bar = screen.getByRole("progressbar", { name: "Attempts finished" });
  expect(bar.getAttribute("aria-valuenow")).toBe("9");
  expect(bar.getAttribute("aria-valuemax")).toBe("45");
  expect(bar.children).toHaveLength(40);
  expect(bar.querySelectorAll(".bg-ink")).toHaveLength(8);
  expect(screen.getByText("Live")).toBeTruthy();
  expect(screen.getByText("09/45", { exact: false })).toBeTruthy();
});

const run = (over: Partial<Run> = {}): Run => ({
  id: "11111111-2222-3333-4444-555555555555",
  suite_id: "s",
  suite_version: 1,
  agent_id: null,
  agent_name: "support",
  status: "completed",
  model: null,
  git_sha: null,
  branch: "main",
  pr_number: null,
  runs_per_case: 10,
  mock_mode: true,
  attempts_total: 20,
  attempts_done: 20,
  pass_rate: 0.5,
  ci_lower: 0.31,
  ci_upper: 0.69,
  total_tokens: null,
  total_cost: null,
  judge_cost_usd: 0,
  error: null,
  created_at: "2026-10-14T10:00:00Z",
  started_at: null,
  finished_at: null,
  suite_name: "support",
  agent: "support",
  shared: false,
  share_expires_at: null,
  ...over,
});

const side = (passes: number, attempts: number) => ({
  passes,
  attempts,
  errors: 0,
  mean_score: null,
  mean_latency_ms: null,
  cost_usd: null,
  pass_rate: passes / attempts,
  label: passes === attempts ? "stable-pass" : passes === 0 ? "stable-fail" : "flaky",
});

const REPORT: RegressionReportDump = {
  verdict: "regression",
  alpha: 0.05,
  alpha_cases: 0.025,
  alpha_suite: 0.025,
  min_drop: 0.05,
  suite: {
    cases: 2,
    baseline_pass_rate: 1,
    candidate_pass_rate: 0.5,
    pass_rate_delta: -0.5,
    p_worse: 0.5,
    p_better: 1,
    exact: true,
    regressed: false,
    improved: false,
    score: null,
    latency_ms: null,
    cost_usd: null,
  },
  cases: [
    ["greeting", side(10, 10), side(10, 10), 0, 1, null],
    ["refund", side(10, 10), side(0, 10), -1, 1 / 184756, 0.025],
  ].map(([id, baseline, candidate, delta, p, threshold]) => ({
    case_id: id as string,
    baseline: baseline as ReturnType<typeof side>,
    candidate: candidate as ReturnType<typeof side>,
    pass_rate_delta: delta as number,
    p_worse: p as number,
    p_worse_min: p as number,
    p_worse_threshold: threshold as number | null,
    p_better: 1,
    p_better_min: 1,
    p_better_threshold: null,
    regressed: id === "refund",
    improved: false,
    score_delta: null,
    latency_delta_ms: null,
    cost_per_attempt_delta_usd: null,
  })) as RegressionReportDump["cases"],
  regressed: ["refund"],
  improved: [],
  newly_failing: ["refund"],
  newly_passing: [],
  newly_flaky: [],
  no_longer_flaky: [],
  added: [],
  removed: [],
};

describe("stats panel", () => {
  test("states the verdict with its counts, p-values, corrected thresholds, effect size and interval", () => {
    const verdict = { branch: "main", baseline_run_id: "b", is_baseline: false, report: REPORT };
    render(
      <>
        <StatsPanel run={run()} rows={[]} verdict={verdict} projectId="p" />
        <CaseTests report={REPORT} compareHref="/compare" />
      </>,
    );
    expect(screen.getByText("95% CI 31.0%–69.0%")).toBeTruthy();
    expect(screen.getByText(/1 case \(refund\) dropped significantly/)).toBeTruthy();
    expect(screen.getByText("20/20 passed", { exact: false })).toBeTruthy(); // baseline
    expect(screen.getByText("10/20 passed", { exact: false })).toBeTruthy(); // this run
    expect(screen.getByText("−50.0 pts")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Per-case tests, most significant first" });
    const [, refund, greeting] = within(table).getAllByRole("row");
    expect(within(refund).getByRole("rowheader").textContent).toBe("refund"); // flagged first
    expect(refund.textContent).toContain("5.4e-6");
    expect(refund.textContent).toContain("0.0250");
    expect(within(refund).getByText("Regressed")).toBeTruthy();
    expect(greeting.textContent).toContain("Not reached");
    expect(screen.getByText(/not an adjusted p-value/)).toBeTruthy();
  });

  test("says plainly when there is nothing to compare against", () => {
    const { rerender } = render(<StatsPanel run={run()} rows={[]} verdict="none" projectId="p" />);
    expect(screen.getByText(/no verdict and no p-value/)).toBeTruthy();
    rerender(<StatsPanel run={run({ status: "running", pass_rate: null })} rows={[]} verdict={null} projectId="p" />);
    expect(screen.getByText("Compared with the baseline when the run finishes.")).toBeTruthy();
    expect(screen.getByText("When the run finishes")).toBeTruthy();
  });

  test("effect sizes read as signed percentage points", () => {
    expect([points(0.125), points(-0.5), points(0)]).toEqual(["+12.5 pts", "−50.0 pts", "±0.0 pts"]);
  });
});

test("failure clusters: a model's words about agent output stay plain, inert text", () => {
  const hostile = "<img src=x onerror=alert(1)> **fix** \u001b[31mred‮txt";
  const { container } = render(
    <FailureClusters
      findings={[{ id: "f", cluster_label: hostile, summary: hostile, suggested_fix: hostile, member_result_ids: ["r1", "r2"] }]}
      caseOf={(id) => (id === "r1" ? "refund" : undefined)}
      projectId="p"
      runId="r"
    />,
  );
  expect(container.querySelector("img, strong, b")).toBeNull();
  expect(container.textContent).toContain("<img src=x onerror=alert(1)> **fix** ␛[31mred⟨U+202E⟩txt");
  expect(container.textContent).not.toMatch(/[\u001b‮]/);
  expect(screen.getByText("refund")).toBeTruthy();
  expect(screen.getByRole("link", { name: "First trace" }).getAttribute("href")).toBe("/projects/p/runs/r/results/r1");
  expect(screen.getByText("2 failing → 1 cluster")).toBeTruthy();
});
