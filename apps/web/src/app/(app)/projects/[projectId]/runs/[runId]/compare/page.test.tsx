import { render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";
import type { CaseSummaryDump, RegressionReportDump } from "@/lib/regression";
import ComparePage from "./page";

// A case id is the suite author's, so it is data: it must reach the page as text.
const CASE = `refund-flow<img src=x onerror="alert(1)">`;

const side = (passes: number, attempts: number): CaseSummaryDump => ({
  passes,
  attempts,
  errors: 0,
  mean_score: null,
  mean_latency_ms: null,
  cost_usd: null,
  pass_rate: passes / attempts,
  label: passes === attempts ? "stable-pass" : passes === 0 ? "stable-fail" : "flaky",
});

const report: RegressionReportDump = {
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
    p_worse: 0.25,
    p_better: 1,
    exact: true,
    regressed: false,
    improved: false,
    score: { baseline: 1, candidate: 0.5, delta: -0.5 },
    latency_ms: null,
    cost_usd: null,
  },
  cases: [
    {
      case_id: CASE,
      baseline: side(5, 5),
      candidate: side(0, 5),
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
    },
    {
      case_id: "greeting",
      baseline: side(5, 5),
      candidate: side(5, 5),
      pass_rate_delta: 0,
      p_worse: 1,
      p_worse_min: 0.004,
      p_worse_threshold: null,
      p_better: 1,
      p_better_min: 0.004,
      p_better_threshold: null,
      regressed: false,
      improved: false,
      score_delta: null,
      latency_delta_ms: null,
      cost_per_attempt_delta_usd: null,
    },
  ],
  regressed: [CASE],
  improved: [],
  newly_failing: [CASE],
  newly_passing: [],
  newly_flaky: [],
  no_longer_flaky: [],
  added: [],
  removed: [],
};

const listItem = (id: string, rate: number, created: string) => ({
  id,
  suite_id: "s1",
  status: "completed",
  created_at: created,
  pass_rate: rate,
  ci_lower: rate - 0.1,
  ci_upper: Math.min(1, rate + 0.1),
  branch: "main",
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "p1", runId: "cand0000-0000" }),
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api/client", () => ({
  api: {
    GET: async (path: string) => {
      if (path === "/runs/{run_id}")
        return {
          data: { id: "cand0000-0000", suite_id: "s1", suite_name: "refund suite", status: "completed", pass_rate: 0.5, ci_lower: 0.3, ci_upper: 0.7, created_at: "2026-10-02T10:00:00Z", finished_at: "2026-10-02T10:01:00Z" },
        };
      if (path === "/projects/{project_id}/runs")
        return { data: [listItem("cand0000-0000", 0.5, "2026-10-02T10:00:00Z"), listItem("base0000-0000", 1, "2026-10-01T10:00:00Z")] };
      if (path === "/runs/{run_id}/verdict")
        return { data: { is_baseline: false, baseline_run_id: "base0000-0000", branch: "main", report }, response: { status: 200 } };
      return { data: undefined, response: { status: 404 } };
    },
  },
}));

const renderPage = () =>
  render(
    <ToastProvider>
      <ComparePage />
    </ToastProvider>,
  );

/** The tile (a <dl>) whose term is `label`. */
const tile = (label: string) => [...document.querySelectorAll("dt")].find((dt) => dt.textContent === label)!.closest("dl")!;

test("the verdict is one bordered sentence of the report's own values; the case id stays text", async () => {
  const { container } = renderPage();

  const verdict = await screen.findByRole("heading", { name: "Verdict" });
  const panel = verdict.closest("section")!;
  const sentence = within(panel).getByText("Regression").closest("p")!;
  expect(sentence.classList.contains("border-fail")).toBe(true);
  expect(sentence.textContent).toBe(`Regression: ${CASE}, p=0.0040, corrected threshold=0.0125`);
  expect(sentence.textContent).not.toMatch(/corrected p/);
  // The prose that explains the test is still there, once.
  expect(screen.getAllByText(/dropped significantly/)).toHaveLength(1);

  expect(container.querySelector("img, script")).toBeNull();
  expect((screen.getByLabelText("Baseline") as HTMLSelectElement).value).toBe("base0000-0000");
});

test("the figures: tiles from the shared cases, whiskers and trend from the runs, each with a table", async () => {
  renderPage();
  await screen.findByRole("heading", { name: "Verdict" });

  const passRate = tile("Pass rate");
  expect(passRate.textContent).toContain("50.0%");
  expect(passRate.textContent).toContain("from 100.0% · −50.0 pts · 2 shared cases");

  const whiskers = screen.getByText("Run pass rate, 95% interval").closest("figure")!;
  const table = whiskers.querySelector("table")!;
  expect(table.textContent).toContain("Baseline100.0%90.0%–100.0%");
  expect(table.textContent).toContain("Candidate50.0%30.0%–70.0%");

  const trend = screen.getByText("Pass rate by run").closest("figure")!;
  expect(trend.querySelector("table")?.textContent).toContain("base0000");

  // One mark per attempt: the case row has 5 passes for the baseline and 5 failures for the candidate.
  const row = screen.getByRole("table", { name: "Case-by-case comparison" }).querySelector("tbody tr")!;
  expect(row.textContent).toContain("5/5");
  expect(row.textContent).toContain("0/5");
  expect(row.querySelectorAll(".bg-current.text-ink")).toHaveLength(5); // baseline passes
  expect(row.querySelectorAll("[aria-hidden] > .mark-fail")).toHaveLength(5); // candidate failures (the badge has its own mark)
  expect(row.textContent).toContain("0.0125"); // the corrected threshold it had to meet
});
