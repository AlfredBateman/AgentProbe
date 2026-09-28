"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { CaseTable } from "@/components/run/case-table";
import { RunStatusBadge, VerdictBadge } from "@/components/run/labels";
import { RunActions } from "@/components/run/run-actions";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Badge } from "@/components/ui/status";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { streamUrl } from "@/lib/api/stream";
import { count, date, duration, pct, usd } from "@/lib/format";
import { type Attempt, attemptKey, caseRows, fromStream, mergeAttempts } from "@/lib/run-cases";
import { type Connection, type Progress, TERMINAL, useRunStream } from "@/lib/use-run-stream";

type Run = components["schemas"]["RunDetailOut"];
type Summary = components["schemas"]["CaseSummaryOut"];
type Verdict = components["schemas"]["RunVerdictOut"] | "none" | null;

export default function RunPage() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>();
  const [run, setRun] = useState<Run | "loading" | "error">("loading");
  const [attempts, setAttempts] = useState<ReadonlyMap<string, Attempt>>(new Map());
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [verdict, setVerdict] = useState<Verdict>(null);

  const loadVerdict = useCallback(async () => {
    const { data, response } = await api.GET("/runs/{run_id}/verdict", { params: { path: { run_id: runId } } });
    setVerdict(data ?? (response.status === 404 ? "none" : null));
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
        const cases = await api.GET("/runs/{run_id}/cases", { params: { path } });
        if (cases.data) setSummaries(cases.data);
        void loadVerdict();
      }
      return next.status;
    });
  }, [runId, loadVerdict]);

  useEffect(() => {
    resync().then((status) => status === null && setRun("error"));
  }, [resync]);

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

  if (run === "loading") return <Skeleton className="h-320" />;
  if (run === "error") return <EmptyState title="Run not found" description="It may have been deleted, or it belongs to another project." />;

  return (
    <>
      <header className="flex flex-col gap-15 desktop:flex-row desktop:items-start desktop:justify-between">
        <div className="min-w-0">
          <p className="text-data-label text-ink-muted">
            <Link href={`/projects/${projectId}`} className="rounded-xs outline-none hover:text-ink focus-visible:shadow-focus">
              Overview
            </Link>{" "}
            / <span className="font-mono">{run.id.slice(0, 8)}</span>
          </p>
          <h1 className="mt-4 font-display text-dash-title-sm break-words tablet:text-dash-title">{run.suite_name}</h1>
          <div className="mt-8 flex flex-wrap items-center gap-8">
            <RunStatusBadge status={run.status} />
            <Badge status="stable">{run.mock_mode ? "Mock LLM" : "Live LLM"}</Badge>
          </div>
          <dl className="mt-12 flex flex-wrap gap-x-20 gap-y-6 text-data">
            <Meta term="Agent">{run.agent}</Meta>
            <Meta term="Branch">{run.branch ?? "—"}</Meta>
            <Meta term="Commit" mono>
              {run.git_sha ? run.git_sha.slice(0, 12) : "—"}
            </Meta>
            <Meta term="Started">{date(run.started_at ?? run.created_at)}</Meta>
          </dl>
        </div>
        <RunActions run={run} projectId={projectId} onChanged={() => void resync()} />
      </header>

      {run.error && (
        <p role="alert" className="mt-20 rounded-lg bg-surface-1 p-15 text-body-sm text-fail">
          {run.error}
        </p>
      )}

      {live && <LivePanel run={run} attempts={attempts} connection={connection} />}

      <SummaryTiles run={run} verdict={verdict} projectId={projectId} />

      <Card title="Cases" className="mt-20">
        <CaseTable
          rows={rows}
          runId={runId}
          projectId={projectId}
          runsPerCase={run.runs_per_case}
          version={`${attempts.size}:${summaries.length}`}
        />
      </Card>
    </>
  );
}

function Meta({ term, mono, children }: { term: string; mono?: boolean; children: ReactNode }) {
  return (
    <div className="flex min-w-0 gap-6">
      <dt className="text-ink-muted">{term}</dt>
      <dd className={mono ? "font-mono text-code text-ink" : "truncate text-ink"}>{children}</dd>
    </div>
  );
}

function useNow(ticking: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!ticking) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [ticking]);
  return now;
}

const CONNECTION: Record<Connection, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  polling: "Live updates unavailable; refreshing every few seconds",
  closed: "Finished",
};

function LivePanel({ run, attempts, connection }: { run: Run; attempts: ReadonlyMap<string, Attempt>; connection: Connection }) {
  const now = useNow(true);
  const list = [...attempts.values()];
  const done = Math.max(run.attempts_done, list.length);
  const total = run.attempts_total;
  const started = run.started_at ? Date.parse(run.started_at) : null;
  const elapsed = started ? now - started : 0;
  const eta = started && done > 0 && done < total ? (elapsed / done) * (total - done) : null;
  const costs = list.map((a) => a.cost).filter((c): c is number => c !== null);
  const tally = (status: string) => list.filter((a) => a.status === status).length;

  return (
    <Card className="mt-20" aria-labelledby="live-title">
      <div className="flex flex-wrap items-baseline justify-between gap-8">
        <h2 id="live-title" className="font-display text-dash-heading">
          {run.status === "queued" ? "Queued" : "Running"}
        </h2>
        <p aria-live="polite" className="text-data-label text-ink-muted">
          {CONNECTION[connection]}
        </p>
      </div>
      {/* A meter: the track is a lighter step of the fill's own neutral, never a status color. */}
      <progress
        max={total}
        value={done}
        aria-label="Attempts finished"
        className="mt-12 block h-8 w-full appearance-none overflow-hidden rounded-pill bg-hairline [&::-moz-progress-bar]:rounded-pill [&::-moz-progress-bar]:bg-ink [&::-webkit-progress-bar]:bg-hairline [&::-webkit-progress-value]:rounded-pill [&::-webkit-progress-value]:bg-ink [&::-webkit-progress-value]:transition-[width] motion-reduce:[&::-webkit-progress-value]:transition-none"
      />
      <dl className="mt-15 grid grid-cols-2 gap-x-20 gap-y-12 text-data tabular-nums tablet:grid-cols-4 desktop:grid-cols-7">
        <Stat term="Attempts">
          {done} / {total}
        </Stat>
        <Stat term="Passed">{tally("passed")}</Stat>
        <Stat term="Failed">{tally("failed")}</Stat>
        <Stat term="Errors">{tally("error")}</Stat>
        <Stat term="Elapsed">{started ? duration(elapsed) : "—"}</Stat>
        <Stat term="Remaining">{eta === null ? "—" : `~${duration(eta)}`}</Stat>
        <Stat term="Cost so far">{costs.length ? usd(costs.reduce((a, b) => a + b, 0)) : "—"}</Stat>
      </dl>
    </Card>
  );
}

function Stat({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <dt className="text-data-label text-ink-muted">{term}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  );
}

function SummaryTiles({ run, verdict, projectId }: { run: Run; verdict: Verdict; projectId: string }) {
  const report = verdict && verdict !== "none" ? verdict.report : null;
  const suite = report?.suite as { pass_rate_delta?: number } | undefined;
  const regressed = (report?.regressed as string[] | undefined) ?? [];
  const judge = run.judge_cost_usd ?? 0;

  return (
    <div className="mt-20 grid grid-cols-2 gap-12 tablet:grid-cols-4">
      <Tile label="Pass rate" className="col-span-2 tablet:row-span-2">
        <p className="font-display text-dash-title text-ink">{pct(run.pass_rate)}</p>
        <p className="mt-4 text-data text-ink-muted tabular-nums">
          {run.ci_lower != null && run.ci_upper != null
            ? `95% CI ${pct(run.ci_lower)}–${pct(run.ci_upper)}`
            : run.status === "completed"
              ? "No interval"
              : "Computed when the run finishes"}
        </p>
        <p className="mt-12 text-data text-ink-muted">
          {run.runs_per_case} attempts per case · {count(run.attempts_total)} attempts
        </p>
      </Tile>
      <Tile label="Verdict vs baseline">
        {verdict === null ? (
          <Skeleton className="h-24 w-120" />
        ) : verdict === "none" ? (
          <p className="text-body-sm text-ink-muted">No baseline on {run.branch ?? "main"}</p>
        ) : verdict.is_baseline ? (
          <p className="text-body-sm text-ink">This run is the {verdict.branch} baseline</p>
        ) : report ? (
          <>
            <VerdictBadge verdict={String(report.verdict)} />
            <p className="mt-6 text-data text-ink-muted">
              {suite?.pass_rate_delta != null && `${suite.pass_rate_delta > 0 ? "+" : ""}${pct(suite.pass_rate_delta)} · `}
              vs{" "}
              <Link
                href={`/projects/${projectId}/runs/${verdict.baseline_run_id}`}
                className="rounded-xs text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
              >
                {verdict.branch} baseline
              </Link>
            </p>
            {regressed.length > 0 && (
              <p className="mt-4 text-data text-ink-muted">
                Regressed: <span className="font-mono text-code text-ink">{regressed.join(", ")}</span>
              </p>
            )}
          </>
        ) : (
          <p className="text-body-sm text-ink-muted">Compared when the run completes</p>
        )}
      </Tile>
      <Tile label="Cost">
        <p className="font-display text-dash-heading">{usd(run.total_cost)}</p>
        <p className="mt-4 text-data text-ink-muted">+ {usd(judge)} judging</p>
      </Tile>
      <Tile label="Tokens">
        <p className="font-display text-dash-heading">{count(run.total_tokens)}</p>
      </Tile>
      <Tile label="Model">
        <p className="font-display text-dash-heading break-words">{run.model ?? "—"}</p>
      </Tile>
    </div>
  );
}

function Tile({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <section aria-label={label} className={`min-w-0 rounded-xl bg-surface-1 p-20 ${className ?? ""}`}>
      <h2 className="mb-8 text-data-label text-ink-muted">{label}</h2>
      {children}
    </section>
  );
}
