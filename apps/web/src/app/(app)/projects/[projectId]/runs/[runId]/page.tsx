"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { CaseBoard, ProgressStrip } from "@/components/run/board";
import { CaseTable } from "@/components/run/case-table";
import { FailureClusters, type Findings } from "@/components/run/failure-clusters";
import { RunStatusBadge } from "@/components/run/labels";
import { RunActions } from "@/components/run/run-actions";
import { CaseTests, StatsPanel, type Verdict } from "@/components/run/stats-panel";
import { PageHeader } from "@/components/shell/page-header";
import { PlainText } from "@/components/ui/code";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/status";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { streamUrl } from "@/lib/api/stream";
import { count, date, usd } from "@/lib/format";
import type { RegressionReportDump } from "@/lib/regression";
import { boardCells } from "@/lib/run-board";
import { type Attempt, attemptKey, caseRows, fromStream, mergeAttempts } from "@/lib/run-cases";
import { type Progress, TERMINAL, useRunStream } from "@/lib/use-run-stream";

type Run = components["schemas"]["RunDetailOut"];
type Summary = components["schemas"]["CaseSummaryOut"];

/**
 * A run as a live board: the segmented progress strip while it runs, one cell per case changing
 * state as attempts land, the statistics and the verdict once it ends, the failure clusters,
 * and the cases table. Live updates come from the run's SSE stream (useRunStream: reconnects,
 * resyncs, falls back to polling); every state is also reachable from a plain reload.
 */
export default function RunPage() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>();
  const [run, setRun] = useState<Run | "loading" | "error">("loading");
  const [attempts, setAttempts] = useState<ReadonlyMap<string, Attempt>>(new Map());
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [verdict, setVerdict] = useState<Verdict>(null);
  const [findings, setFindings] = useState<Findings>(null);
  const [caseIds, setCaseIds] = useState<string[]>([]);

  const loadVerdict = useCallback(async () => {
    const { data, response } = await api.GET("/runs/{run_id}/verdict", { params: { path: { run_id: runId } } });
    setVerdict(data ?? (response.status === 404 ? "none" : null));
  }, [runId]);

  const loadFindings = useCallback(async () => {
    setFindings((f) => (Array.isArray(f) ? f : "loading"));
    const { data } = await api.GET("/runs/{run_id}/findings", { params: { path: { run_id: runId } } });
    setFindings(data ?? "error");
  }, [runId]);

  /** The authoritative state; merged into (never replacing) what the stream delivered. */
  const resync = useCallback(() => {
    const path = { run_id: runId };
    return Promise.all([
      api.GET("/runs/{run_id}", { params: { path } }),
      api.GET("/runs/{run_id}/results", { params: { path } }),
    ]).then(async ([runRes, results]) => {
      if (!runRes.data) return null;
      const next = runRes.data;
      setRun(next);
      if (results.data) setAttempts((known) => mergeAttempts(known, results.data));
      if (TERMINAL.has(next.status)) {
        // Independent reads: none waits for another.
        void loadVerdict();
        void loadFindings();
        const cases = await api.GET("/runs/{run_id}/cases", { params: { path } });
        if (cases.data) setSummaries(cases.data);
      }
      return next.status;
    });
  }, [runId, loadVerdict, loadFindings]);

  useEffect(() => {
    resync().then((status) => status === null && setRun("error"));
  }, [resync]);

  // The suite version's cases, so every cell is on the board before its first attempt.
  const suiteId = typeof run === "object" ? run.suite_id : null;
  const version = typeof run === "object" ? run.suite_version : null;
  useEffect(() => {
    if (!suiteId || version === null) return;
    api
      .GET("/suites/{suite_id}/cases", { params: { path: { suite_id: suiteId }, query: { version } } })
      .then(({ data }) => data && setCaseIds(data.map((c) => c.id)));
  }, [suiteId, version]);

  const live = typeof run === "object" && !TERMINAL.has(run.status);
  const connection = useRunStream({
    runId,
    resolveUrl: () => streamUrl(runId),
    enabled: live,
    resync,
    onProgress: (p: Progress) =>
      setRun((r) =>
        typeof r === "object"
          ? { ...r, status: p.status, attempts_done: Math.max(r.attempts_done, p.done), attempts_total: p.total, error: p.error }
          : r,
      ),
    onAttempt: (a) => {
      setAttempts((known) => (known.has(attemptKey(a)) ? known : mergeAttempts(known, [fromStream(a)])));
      setRun((r) => (typeof r === "object" ? { ...r, attempts_done: Math.max(r.attempts_done, a.done) } : r));
    },
  });

  const rows = useMemo(() => caseRows(attempts.values(), summaries), [attempts, summaries]);
  const runsPerCase = typeof run === "object" ? run.runs_per_case : 1;
  const cells = useMemo(() => boardCells(caseIds, rows, runsPerCase, live), [caseIds, rows, runsPerCase, live]);
  const caseOf = useMemo(() => {
    const byId = new Map([...attempts.values()].map((a) => [a.id, a.case]));
    return (id: string) => byId.get(id);
  }, [attempts]);

  const report = verdict && verdict !== "none" ? (verdict.report as RegressionReportDump | null) : null;

  if (run === "loading") return <Skeleton className="h-320" />;
  if (run === "error") return <EmptyState title="Run not found" description="It may have been deleted, or it belongs to another project." />;

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            [{" "}
            <Link href={`/projects/${projectId}/runs`} className="hover:text-ink">
              Runs
            </Link>{" "}
            ] <span aria-hidden>{"///"}</span> <span className="type-code">{run.id.slice(0, 8)}</span>
          </>
        }
        title={run.suite_name}
        verbatim
        actions={<RunActions run={run} projectId={projectId} onChanged={() => void resync()} />}
      >
        <div className="flex flex-wrap items-center gap-8">
          <RunStatusBadge status={run.status} />
          <Badge status="stable">{run.mock_mode ? "Mock LLM" : "Live LLM"}</Badge>
        </div>
        <dl className="mt-12 flex flex-wrap gap-x-20 gap-y-6">
          <Meta term="Agent">{run.agent}</Meta>
          <Meta term="Branch">{run.branch ?? "—"}</Meta>
          <Meta term="Commit">{run.git_sha ? run.git_sha.slice(0, 12) : "—"}</Meta>
          <Meta term="Started">{date(run.started_at ?? run.created_at)}</Meta>
          <Meta term="Cost">{usd(run.total_cost)}</Meta>
          <Meta term="Judging">{usd(run.judge_cost_usd ?? 0)}</Meta>
          <Meta term="Tokens">{count(run.total_tokens)}</Meta>
        </dl>
      </PageHeader>

      {run.error && (
        <div role="alert" className="mt-24 border border-fail p-16">
          <p className="mb-6 type-label text-fail">Run error</p>
          <PlainText text={run.error} mono={false} />
        </div>
      )}

      {live && (
        <ProgressStrip
          status={run.status}
          done={Math.max(run.attempts_done, attempts.size)}
          total={run.attempts_total}
          startedAt={run.started_at}
          attempts={[...attempts.values()]}
          connection={connection}
        />
      )}

      <div className="mt-24 grid items-start gap-24 desktop:grid-cols-[minmax(0,1fr)_minmax(0,460px)]">
        <CaseBoard cells={cells} projectId={projectId} runId={runId} />
        <StatsPanel run={run} rows={rows} verdict={verdict} projectId={projectId} />
      </div>

      {report && (
        <div className="mt-24">
          <CaseTests report={report} compareHref={`/projects/${projectId}/runs/${run.id}/compare`} />
        </div>
      )}

      <div className="mt-24">
        <FailureClusters findings={findings} caseOf={caseOf} projectId={projectId} runId={runId} />
      </div>

      <Panel title="Cases" titleStyle="label" className="mt-24">
        <CaseTable rows={rows} runId={runId} projectId={projectId} runsPerCase={run.runs_per_case} version={`${attempts.size}:${summaries.length}`} />
      </Panel>
    </>
  );
}

/** Interface words in micro type; the value is data (an agent name, a branch), kept as written. */
function Meta({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 items-baseline gap-6">
      <dt className="type-micro text-ink-muted">{term}</dt>
      <dd className="truncate type-code text-ink">{children}</dd>
    </div>
  );
}
