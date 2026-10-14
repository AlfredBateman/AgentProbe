"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Label, Select } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Stat, StatGrid } from "@/components/ui/stat";
import { Badge } from "@/components/ui/status";
import { AttemptStrip, ChartFigure, ChartTable, RateWhiskers, RunTrend, type TrendPoint, type WhiskerRow } from "@/components/ui/telemetry";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { cx } from "@/lib/cx";
import { date, ms, pValue, pct, score, usd } from "@/lib/format";
import {
  type CaseComparisonDump,
  type MetricDeltaDump,
  points,
  type RegressionReportDump,
  verdictLine,
  verdictSummary,
} from "@/lib/regression";
import { trendPoints } from "@/lib/trends";

type Run = components["schemas"]["RunDetailOut"];
type RunListItem = components["schemas"]["RunListOut"];

/** A resolved comparison: which baseline it's against, and the report itself. `"is_baseline"`:
 * this run *is* its branch's baseline, so there's nothing meaningful to diff it against by
 * default (the picker above still lets the user choose a different one). */
type Comparison = { baselineRunId: string; report: RegressionReportDump } | "is_baseline";

const RUNS_SHOWN = 50;

export default function ComparePage() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>();
  const [run, setRun] = useState<Run | "loading" | "error">("loading");
  const [suiteRuns, setSuiteRuns] = useState<RunListItem[]>([]);
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
      .GET("/projects/{project_id}/runs", { params: { path: { project_id: projectId }, query: { suite_id: suiteId, limit: RUNS_SHOWN } } })
      .then(({ data }) => setSuiteRuns((data ?? []).filter((r) => r.status === "completed")));
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

  const choices = suiteRuns.filter((r) => r.id !== runId);

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            [{" "}
            <Link href={`/projects/${projectId}/runs/${runId}`} className="hover:text-ink">
              Run <span className="type-code">{runId.slice(0, 8)}</span>
            </Link>{" "}
            ] <span aria-hidden>{"///"}</span> Compare
          </>
        }
        title={run.suite_name}
        verbatim
      >
        <p className="type-data text-ink-muted">
          Candidate <span className="type-code text-ink">{runId.slice(0, 8)}</span>, {date(run.finished_at ?? run.created_at)}
        </p>
      </PageHeader>

      <Panel className="mt-24">
        <div className="flex flex-wrap items-end gap-x-16 gap-y-12">
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
              {choices.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.branch ? `${r.branch} · ` : ""}
                  {date(r.created_at)} ({r.id.slice(0, 8)})
                </option>
              ))}
            </Select>
          </div>
          <p className="max-w-420 type-body-sm text-ink-muted">Candidate and baseline are compared case by case on the cases they share.</p>
        </div>
      </Panel>

      {comparison === null && (
        <div className="mt-24">
          <EmptyState
            title="No baseline to compare with"
            description={choices.length ? "Pick a run above to compare against." : "There's only one completed run of this suite so far."}
          />
        </div>
      )}
      {comparison === "loading" && <Skeleton className="mt-24 h-320" />}
      {comparison === "error" && (
        <div className="mt-24">
          <EmptyState title="Couldn't compare these runs" description="They may not share a suite, or one of them may not exist any more." />
        </div>
      )}
      {comparison === "is_baseline" && (
        <div className="mt-24">
          <EmptyState title="This run is the baseline" description="Pick a different run above to compare it against." />
        </div>
      )}
      {comparison !== null && typeof comparison === "object" && (
        <CompareView
          report={comparison.report}
          run={run}
          suiteRuns={suiteRuns}
          projectId={projectId}
          baselineRunId={comparison.baselineRunId}
          candidateRunId={runId}
        />
      )}
    </>
  );
}

const VERDICT_STYLE = {
  regression: { box: "border-fail", word: "bg-fail text-on-fail" },
  improvement: { box: "border-accent", word: "border border-accent text-accent" },
  no_change: { box: "border-ink", word: "border border-ink text-ink" },
} as const;

/** The verdict as one bordered sentence, built from the report's own values. */
function VerdictSentence({ report }: { report: RegressionReportDump }) {
  const line = verdictLine(report);
  const style = VERDICT_STYLE[line.verdict];
  return (
    <p className={cx("border p-12 type-code", style.box)}>
      <span className={cx("inline-block px-8 py-3 type-label", style.word)}>{line.word}</span>
      {": "}
      {line.detail}
    </p>
  );
}

function CompareView({
  report,
  run,
  suiteRuns,
  projectId,
  baselineRunId,
  candidateRunId,
}: {
  report: RegressionReportDump;
  run: Run;
  suiteRuns: RunListItem[];
  projectId: string;
  baselineRunId: string;
  candidateRunId: string;
}) {
  const suite = report.suite;
  const baselineRun = suiteRuns.find((r) => r.id === baselineRunId);
  const regression = report.verdict === "regression";
  const diff = { projectId, baselineRunId, candidateRunId };

  const columns: Column<CaseComparisonDump>[] = [
    { key: "case", header: "Case", value: (c) => c.case_id, render: (c) => <span className="type-code">{c.case_id}</span> },
    {
      key: "baseline",
      header: "Baseline",
      value: (c) => c.baseline.pass_rate,
      align: "right",
      render: (c) => <Attempts side={c.baseline} tone="baseline" />,
    },
    {
      key: "candidate",
      header: "Candidate",
      value: (c) => c.candidate.pass_rate,
      align: "right",
      render: (c) => <Attempts side={c.candidate} tone="candidate" />,
    },
    {
      key: "delta",
      header: "Δ pass rate",
      value: (c) => c.pass_rate_delta,
      align: "right",
      render: (c) => <span className={c.regressed ? "text-fail" : undefined}>{points(c.pass_rate_delta)}</span>,
    },
    { key: "p", header: "p (worse)", value: (c) => c.p_worse, align: "right", render: (c) => pValue(c.p_worse) },
    {
      key: "threshold",
      header: "Corrected threshold",
      value: (c) => c.p_worse_threshold,
      align: "right",
      render: (c) => (c.p_worse_threshold === null ? <span className="text-ink-muted">Not reached</span> : pValue(c.p_worse_threshold)),
    },
    {
      key: "verdict",
      header: "Verdict",
      align: "right",
      render: (c) =>
        c.regressed ? <Badge status="fail">Regressed</Badge> : c.improved ? <Badge status="pass">Improved</Badge> : <span className="text-ink-muted">—</span>,
    },
    {
      key: "trace",
      header: "Trace",
      align: "right",
      render: (c) => (
        <DiffLink {...diff} caseId={c.case_id} label={`${c.case_id}: side by side`}>
          Side by side
        </DiffLink>
      ),
    },
  ];

  // The runs' own pass rates and 95% intervals, as the API stores them. The tile above counts
  // only the cases both runs share, so the two can differ when the suite changed between them.
  const whiskers: WhiskerRow[] = [
    { label: "Baseline", tone: "baseline", value: baselineRun?.pass_rate ?? suite?.baseline_pass_rate ?? null, lower: baselineRun?.ci_lower ?? null, upper: baselineRun?.ci_upper ?? null },
    { label: "Candidate", tone: "candidate", value: run.pass_rate ?? suite?.candidate_pass_rate ?? null, lower: run.ci_lower ?? null, upper: run.ci_upper ?? null },
  ];
  const trend: TrendPoint[] = trendPoints(suiteRuns, run.suite_id).map((p) => ({
    id: p.id,
    rate: p.pass,
    role: p.id === candidateRunId ? "candidate" : p.id === baselineRunId ? "baseline" : undefined,
  }));
  const interval = (w: WhiskerRow) => (w.lower !== null && w.upper !== null ? `${pct(w.lower)}–${pct(w.upper)}` : "No interval");

  return (
    <>
      <Panel title="Verdict" className="mt-24" actions={<span className="type-micro text-ink-muted tabular-nums">
            <span className="normal-case">α</span> {report.alpha} · min drop {pct(report.min_drop, 0)}
          </span>}>
        <VerdictSentence report={report} />
        <p className="mt-12 max-w-680 type-body-sm text-ink-muted">{verdictSummary(report) || "No shared cases to compare."}</p>
      </Panel>

      {suite && (
        <StatGrid className="mt-24">
          <Stat
            label="Pass rate"
            value={pct(suite.candidate_pass_rate)}
            tone={regression && suite.pass_rate_delta < 0 ? "fail" : undefined}
            note={`from ${pct(suite.baseline_pass_rate)} · ${points(suite.pass_rate_delta)} · ${suite.cases} shared cases`}
          />
          <MetricStat label="Score" metric={suite.score} format={score} />
          <MetricStat label="Latency" metric={suite.latency_ms} format={ms} />
          <MetricStat label="Cost / attempt" metric={suite.cost_usd} format={usd} />
        </StatGrid>
      )}

      <div className="mt-24 grid items-start gap-16 desktop:grid-cols-2">
        <ChartFigure
          title="Run pass rate, 95% interval"
          note="Scale 0 to 100%"
          table={
            <ChartTable
              caption="Pass rate and 95% interval of the baseline and the candidate"
              head={["Run", "Pass rate", "95% interval"]}
              rows={whiskers.map((w) => [w.label, pct(w.value), interval(w)])}
            />
          }
        >
          <RateWhiskers rows={whiskers} />
        </ChartFigure>
        <ChartFigure
          title="Pass rate by run"
          note={suiteRuns.length >= RUNS_SHOWN ? `Newest ${RUNS_SHOWN} runs` : `${trend.length} ${trend.length === 1 ? "run" : "runs"}`}
          table={
            <ChartTable
              caption="Pass rate of each completed run of this suite, oldest first"
              head={["Run", "Date", "Pass rate", "Role"]}
              rows={trendPoints(suiteRuns, run.suite_id).map((p) => [
                p.id.slice(0, 8),
                date(p.at),
                pct(p.pass),
                p.id === candidateRunId ? "Candidate" : p.id === baselineRunId ? "Baseline" : "",
              ])}
            />
          }
        >
          <RunTrend points={trend} />
        </ChartFigure>
      </div>

      <div className="mt-24 grid gap-16 tablet:grid-cols-2">
        <Transition title="Newly failing" cases={report.newly_failing} tone="fail" {...diff} />
        <Transition title="Newly passing" cases={report.newly_passing} {...diff} />
        <Transition title="Newly flaky" cases={report.newly_flaky} {...diff} />
        <Transition title="No longer flaky" cases={report.no_longer_flaky} {...diff} />
      </div>

      {report.cases.length > 0 && (
        <Panel
          title="Cases"
          titleStyle="label"
          className="mt-24"
          actions={<span className="type-micro text-ink-muted tabular-nums">{report.cases.length} shared</span>}
        >
          <div className="-mx-16 -mt-16">
            <DataTable caption="Case-by-case comparison" columns={columns} rows={report.cases} rowKey={(c) => c.case_id} />
          </div>
          {(report.added.length > 0 || report.removed.length > 0) && (
            <p className="mt-12 border-t border-hairline pt-12 type-body-sm text-ink-muted">
              {report.added.length > 0 && `${report.added.length} only in the candidate. `}
              {report.removed.length > 0 && `${report.removed.length} only in the baseline.`}
            </p>
          )}
        </Panel>
      )}
    </>
  );
}

/** A side's passes over its attempts, with one mark per attempt. */
function Attempts({ side, tone }: { side: CaseComparisonDump["baseline"]; tone: "baseline" | "candidate" }) {
  return (
    <span className="inline-flex flex-col items-end gap-4">
      <span>
        {side.passes}/{side.attempts}
      </span>
      <span className="max-w-132">
        <AttemptStrip passes={side.passes} attempts={side.attempts} errors={side.errors} tone={tone} />
      </span>
    </span>
  );
}

function MetricStat({ label, metric, format }: { label: string; metric: MetricDeltaDump | null; format: (x: number | null) => string }) {
  if (!metric) return <Stat label={label} value="—" note="No data" />;
  const sign = metric.delta > 0 ? "+" : metric.delta < 0 ? "−" : "±";
  return <Stat label={label} value={format(metric.candidate)} note={`from ${format(metric.baseline)} · ${sign}${format(Math.abs(metric.delta))} avg. per case`} />;
}

function Transition({
  title,
  cases,
  tone,
  ...diff
}: {
  title: string;
  cases: string[];
  tone?: "fail";
  projectId: string;
  baselineRunId: string;
  candidateRunId: string;
}) {
  if (cases.length === 0) return null;
  return (
    <Panel title={`${title} (${cases.length})`} titleStyle="label">
      <ul className="flex flex-wrap gap-8">
        {cases.map((c) => (
          <li key={c}>
            <DiffLink {...diff} caseId={c} tone={tone}>
              {c}
            </DiffLink>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** Fetches each run's attempt for this case and opens the candidate's trace, side by side with
 * the baseline's (the trace viewer's own `?compare=` picker, ADR 0031). */
function DiffLink({
  projectId,
  baselineRunId,
  candidateRunId,
  caseId,
  label,
  tone,
  children,
}: {
  projectId: string;
  baselineRunId: string;
  candidateRunId: string;
  caseId: string;
  label?: string;
  tone?: "fail";
  children: string;
}) {
  const router = useRouter();
  const toast = useToast();
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
    if (!c) {
      toast({ title: `The candidate run has no attempt of ${caseId}`, tone: "fail" });
      return;
    }
    router.push(`/projects/${projectId}/runs/${candidateRunId}/results/${c.id}${b ? `?compare=${b.id}` : ""}`);
  }

  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => void go()}
      disabled={busy}
      className={cx(
        "inline-flex min-h-40 cursor-pointer items-center border bg-canvas px-12 type-code text-ink hover:border-ink disabled:opacity-50 pointer-coarse:min-h-44",
        tone === "fail" ? "border-fail" : "border-hairline-strong",
      )}
    >
      {children}
    </button>
  );
}
