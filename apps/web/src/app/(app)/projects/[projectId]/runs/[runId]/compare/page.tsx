"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { VerdictBadge } from "@/components/run/labels";
import { Card } from "@/components/ui/card";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Label, Select } from "@/components/ui/field";
import { Badge } from "@/components/ui/status";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { date, ms, pct, score, usd } from "@/lib/format";
import { type CaseComparisonDump, type MetricDeltaDump, type RegressionReportDump, signedPct, verdictSummary } from "@/lib/regression";

type Run = components["schemas"]["RunDetailOut"];
type RunListItem = components["schemas"]["RunListOut"];

/** A resolved comparison: which baseline it's against, and the report itself. `"is_baseline"`:
 * this run *is* its branch's baseline, so there's nothing meaningful to diff it against by
 * default (the picker above still lets the user choose a different one). */
type Comparison = { baselineRunId: string; report: RegressionReportDump } | "is_baseline";

export default function ComparePage() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>();
  const [run, setRun] = useState<Run | "loading" | "error">("loading");
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [baselineId, setBaselineId] = useState<string | null>(null);
  const [comparison, setComparison] = useState<Comparison | "loading" | "error" | null>(null);

  useEffect(() => {
    api.GET("/runs/{run_id}", { params: { path: { run_id: runId } } }).then(({ data }) => setRun(data ?? "error"));
  }, [runId]);

  const pickBaseline = useCallback(
    async (id: string) => {
      setBaselineId(id);
      setComparison("loading");
      const { data } = await api.GET("/runs/compare", { params: { query: { a: id, b: runId } } });
      setComparison(data ? { baselineRunId: id, report: data.report as unknown as RegressionReportDump } : "error");
    },
    [runId],
  );

  useEffect(() => {
    if (typeof run !== "object") return;
    const suiteId = run.suite_id;
    api
      .GET("/projects/{project_id}/runs", { params: { path: { project_id: projectId }, query: { suite_id: suiteId, limit: 50 } } })
      .then(({ data }) => setRuns((data ?? []).filter((r) => r.id !== runId && r.status === "completed")));
    // Default: the branch's own baseline (same as the run page's "vs baseline" tile).
    api.GET("/runs/{run_id}/verdict", { params: { path: { run_id: runId } } }).then(({ data, response }) => {
      if (response.status === 404) {
        setComparison(null);
        return;
      }
      if (!data) {
        setComparison("error");
        return;
      }
      if (data.is_baseline) {
        setComparison("is_baseline");
        return;
      }
      setBaselineId(data.baseline_run_id);
      setComparison(data.report ? { baselineRunId: data.baseline_run_id, report: data.report as unknown as RegressionReportDump } : "error");
    });
  }, [projectId, runId, run]);

  if (run === "loading") return <Skeleton className="h-320" />;
  if (run === "error") return <EmptyState title="Run not found" description="It may have been deleted, or it belongs to another project." />;

  return (
    <>
      <p className="text-data-label text-ink-muted">
        <Link href={`/projects/${projectId}/runs/${runId}`} className="rounded-xs outline-none hover:text-ink focus-visible:shadow-focus">
          Run <span className="font-mono">{runId.slice(0, 8)}</span>
        </Link>{" "}
        / Compare
      </p>
      <h1 className="mt-4 font-display text-dash-title-sm break-words tablet:text-dash-title">{run.suite_name}</h1>

      <Card className="mt-20">
        <div className="flex flex-wrap items-end gap-12">
          <div className="flex flex-col gap-6">
            <Label htmlFor="baseline-picker">Baseline</Label>
            <Select
              id="baseline-picker"
              className="min-w-240"
              value={baselineId ?? ""}
              onChange={(e) => e.target.value && void pickBaseline(e.target.value)}
            >
              <option value="" disabled>
                Choose a run
              </option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.branch ? `${r.branch} · ` : ""}
                  {date(r.created_at)} ({r.id.slice(0, 8)})
                </option>
              ))}
            </Select>
          </div>
          <p className="text-data text-ink-muted">
            vs candidate <span className="font-mono text-code text-ink">{runId.slice(0, 8)}</span> ({date(run.finished_at ?? run.created_at)})
          </p>
        </div>
      </Card>

      {comparison === null && (
        <div className="mt-20">
          <EmptyState
            title="No baseline to compare with"
            description={runs.length ? "Pick a run above to compare against." : "There's only one completed run of this suite so far."}
          />
        </div>
      )}
      {comparison === "loading" && <Skeleton className="mt-20 h-320" />}
      {comparison === "error" && (
        <div className="mt-20">
          <EmptyState title="Couldn't compare these runs" description="They may not share a suite, or one of them may not exist any more." />
        </div>
      )}
      {comparison === "is_baseline" && (
        <div className="mt-20">
          <EmptyState title="This run is the baseline" description="Pick a different run above to compare it against." />
        </div>
      )}
      {comparison !== null && typeof comparison === "object" && (
        <CompareView report={comparison.report} projectId={projectId} baselineRunId={comparison.baselineRunId} candidateRunId={runId} />
      )}
    </>
  );
}

function CompareView({
  report,
  projectId,
  baselineRunId,
  candidateRunId,
}: {
  report: RegressionReportDump;
  projectId: string;
  baselineRunId: string;
  candidateRunId: string;
}) {
  const suite = report.suite;
  const columns: Column<CaseComparisonDump>[] = [
    { key: "case", header: "Case", value: (c) => c.case_id, render: (c) => <span className="font-mono text-code">{c.case_id}</span> },
    {
      key: "baseline",
      header: "Baseline",
      value: (c) => c.baseline.pass_rate,
      align: "right",
      render: (c) => `${c.baseline.passes}/${c.baseline.attempts}`,
    },
    {
      key: "candidate",
      header: "Candidate",
      value: (c) => c.candidate.pass_rate,
      align: "right",
      render: (c) => `${c.candidate.passes}/${c.candidate.attempts}`,
    },
    { key: "delta", header: "Δ pass rate", value: (c) => c.pass_rate_delta, align: "right", render: (c) => signedPct(c.pass_rate_delta) },
    { key: "p", header: "p (worse)", value: (c) => c.p_worse, align: "right", render: (c) => c.p_worse.toFixed(4) },
    {
      key: "verdict",
      header: "Verdict",
      align: "right",
      render: (c) => (c.regressed ? <Badge status="fail">Regressed</Badge> : c.improved ? <Badge status="pass">Improved</Badge> : <span className="text-ink-muted">—</span>),
    },
    {
      key: "trace",
      header: "Trace",
      align: "right",
      render: (c) => <DiffLink projectId={projectId} baselineRunId={baselineRunId} candidateRunId={candidateRunId} caseId={c.case_id} />,
    },
  ];

  return (
    <>
      <Card title="Verdict" className="mt-20">
        <VerdictBadge verdict={report.verdict} />
        <p className="mt-8 text-body text-ink">{verdictSummary(report) || "No shared cases to compare."}</p>
      </Card>

      {suite && (
        <div className="mt-20 grid grid-cols-2 gap-12 tablet:grid-cols-4">
          <Tile label="Pass rate">
            <p className="font-display text-dash-heading">
              {pct(suite.baseline_pass_rate)} → {pct(suite.candidate_pass_rate)}
            </p>
            <p className="mt-4 text-data text-ink-muted">
              {signedPct(suite.pass_rate_delta)} over {suite.cases} shared cases
            </p>
          </Tile>
          <MetricTile label="Score" metric={suite.score} format={score} />
          <MetricTile label="Latency" metric={suite.latency_ms} format={ms} />
          <MetricTile label="Cost / attempt" metric={suite.cost_usd} format={usd} />
        </div>
      )}

      <TransitionSection title="Newly failing" cases={report.newly_failing} projectId={projectId} baselineRunId={baselineRunId} candidateRunId={candidateRunId} />
      <TransitionSection title="Newly passing" cases={report.newly_passing} projectId={projectId} baselineRunId={baselineRunId} candidateRunId={candidateRunId} />
      <TransitionSection title="Newly flaky" cases={report.newly_flaky} projectId={projectId} baselineRunId={baselineRunId} candidateRunId={candidateRunId} />
      <TransitionSection title="No longer flaky" cases={report.no_longer_flaky} projectId={projectId} baselineRunId={baselineRunId} candidateRunId={candidateRunId} />

      {report.cases.length > 0 && (
        <Card title="Cases" className="mt-20">
          <DataTable caption="Case-by-case comparison" columns={columns} rows={report.cases} rowKey={(c) => c.case_id} />
          {(report.added.length > 0 || report.removed.length > 0) && (
            <p className="mt-12 text-data text-ink-muted">
              {report.added.length > 0 && `${report.added.length} only in the candidate. `}
              {report.removed.length > 0 && `${report.removed.length} only in the baseline.`}
            </p>
          )}
        </Card>
      )}
    </>
  );
}

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section aria-label={label} className="min-w-0 rounded-xl bg-surface-1 p-20">
      <h2 className="mb-8 text-data-label text-ink-muted">{label}</h2>
      {children}
    </section>
  );
}

function MetricTile({ label, metric, format }: { label: string; metric: MetricDeltaDump | null; format: (x: number | null) => string }) {
  return (
    <Tile label={label}>
      {metric ? (
        <>
          <p className="font-display text-dash-heading">
            {format(metric.baseline)} → {format(metric.candidate)}
          </p>
          <p className="mt-4 text-data text-ink-muted">{metric.delta >= 0 ? "+" : ""}{format(metric.delta)} avg. per case</p>
        </>
      ) : (
        <p className="text-body-sm text-ink-muted">No data</p>
      )}
    </Tile>
  );
}

function TransitionSection({
  title,
  cases,
  projectId,
  baselineRunId,
  candidateRunId,
}: {
  title: string;
  cases: string[];
  projectId: string;
  baselineRunId: string;
  candidateRunId: string;
}) {
  if (cases.length === 0) return null;
  return (
    <Card title={`${title} (${cases.length})`} className="mt-20">
      <ul className="flex flex-wrap gap-8">
        {cases.map((c) => (
          <li key={c}>
            <DiffLink projectId={projectId} baselineRunId={baselineRunId} candidateRunId={candidateRunId} caseId={c} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Fetches each run's attempt for this case and opens the candidate's trace, side by side with
 * the baseline's (the trace viewer's own `?compare=` picker, ADR 0031). */
function DiffLink({
  projectId,
  baselineRunId,
  candidateRunId,
  caseId,
}: {
  projectId: string;
  baselineRunId: string;
  candidateRunId: string;
  caseId: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function go() {
    setBusy(true);
    const [cand, base] = await Promise.all([
      api.GET("/runs/{run_id}/results", { params: { path: { run_id: candidateRunId }, query: { case: caseId } } }),
      api.GET("/runs/{run_id}/results", { params: { path: { run_id: baselineRunId }, query: { case: caseId } } }),
    ]);
    const c = cand.data?.[0];
    const b = base.data?.[0];
    setBusy(false);
    if (!c) return;
    router.push(`/projects/${projectId}/runs/${candidateRunId}/results/${c.id}${b ? `?compare=${b.id}` : ""}`);
  }

  return (
    <button
      type="button"
      onClick={() => void go()}
      disabled={busy}
      className="inline-flex items-center gap-6 rounded-pill bg-surface-2 px-10 py-6 font-mono text-code text-ink outline-none hover:bg-surface-1 focus-visible:shadow-focus disabled:opacity-50"
    >
      {caseId}
    </button>
  );
}
