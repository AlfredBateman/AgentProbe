"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { RunSuiteDialog } from "@/components/run/run-suite-dialog";
import { RunsTable } from "@/components/run/runs-table";
import { CostChart, LatencyChart, PassRateChart } from "@/components/run/trend-charts";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Label, Select } from "@/components/ui/field";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { date, pct } from "@/lib/format";
import { type Baseline, baselineBranches, defaultSuite, type RunRow, suiteBaseline, trendPoints } from "@/lib/trends";

type Suite = components["schemas"]["SuiteOut"];
type Data = { runs: RunRow[]; baselines: Baseline[]; suites: Suite[] };

// ponytail: the trends read the newest 200 runs; page through `offset` if a suite's history outgrows it.
const TREND_RUNS = 200;
const LATEST = 10;

/** Project overview (E2): one suite's pass-rate, cost and latency trends, the
 * project's latest runs, baselines, and a way to start a run. */
export default function ProjectOverview() {
  const { projectId } = useParams<{ projectId: string }>();
  const [data, setData] = useState<Data | "loading" | "error">("loading");
  const [suiteId, setSuiteId] = useState<string | null>(null);
  const [dialog, setDialog] = useState(false);

  useEffect(() => {
    const path = { project_id: projectId };
    Promise.all([
      api.GET("/projects/{project_id}/runs", { params: { path, query: { limit: TREND_RUNS } } }),
      api.GET("/projects/{project_id}/baselines", { params: { path } }),
      api.GET("/projects/{project_id}/suites", { params: { path } }),
    ])
      .then(([runs, baselines, suites]) =>
        setData(runs.data && baselines.data && suites.data ? { runs: runs.data, baselines: baselines.data, suites: suites.data } : "error"),
      )
      .catch(() => setData("error"));
  }, [projectId]);

  const loaded = typeof data === "object" ? data : null;
  const selected = suiteId ?? (loaded ? (defaultSuite(loaded.runs) ?? loaded.suites[0]?.id ?? null) : null);
  const points = useMemo(() => (loaded && selected ? trendPoints(loaded.runs, selected) : []), [loaded, selected]);
  const branches = useMemo(() => baselineBranches(loaded?.baselines ?? []), [loaded]);

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-12">
      <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Overview</h1>
      <Button data-testid="run-a-suite" onClick={() => setDialog(true)} disabled={!loaded}>
        Run a suite
      </Button>
    </header>
  );
  const runDialog = dialog && loaded && (
    <RunSuiteDialog projectId={projectId} suites={loaded.suites} suiteId={selected ?? undefined} onClose={() => setDialog(false)} />
  );

  if (data === "loading")
    return (
      <>
        {header}
        <Skeleton className="mt-20 h-320" />
      </>
    );
  if (data === "error") return <EmptyState title="Couldn't load this project" description="Check your connection and reload the page." />;

  if (data.runs.length === 0)
    return (
      <>
        {header}
        <Card className="mt-20">
          <EmptyState
            title="No runs yet"
            description={
              data.suites.length
                ? "Start a run of one of this project's suites, or push one from CI."
                : "Add an agent and a suite, then run it here or push a run from CI."
            }
            action={
              data.suites.length ? (
                <Button variant="secondary" onClick={() => setDialog(true)}>
                  Run a suite
                </Button>
              ) : (
                <Link
                  href={`/projects/${projectId}/suites`}
                  className="rounded-xs text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
                >
                  Go to Suites
                </Link>
              )
            }
          />
        </Card>
        {runDialog}
      </>
    );

  const suite = data.suites.find((s) => s.id === selected);
  const suiteRuns = data.runs.filter((r) => r.suite_id === selected);
  const latest = points.at(-1);
  const baseline = selected ? suiteBaseline(data.baselines, selected) : null;
  const baselineRate = baseline?.run.pass_rate ?? null;

  return (
    <>
      {header}

      {/* The one filter row: the suite scopes the tiles and the three trend charts below it. */}
      <div className="mt-20 flex flex-wrap items-center gap-12">
        <Label htmlFor="overview-suite">Suite</Label>
        <Select id="overview-suite" data-testid="overview-suite" value={selected ?? ""} onChange={(e) => setSuiteId(e.target.value)} className="min-w-200">
          {/* Suites with runs, plus any without: runs can only be of a suite that exists. */}
          {data.suites.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <span className="text-data text-ink-muted">
          {points.length} completed {points.length === 1 ? "run" : "runs"}
          {suite && ` · version ${suite.version}, ${suite.case_count} ${suite.case_count === 1 ? "case" : "cases"}`}
        </span>
      </div>

      <div className="mt-15 grid grid-cols-1 gap-12 tablet:grid-cols-3">
        <Tile label="Latest pass rate">
          <p className="font-display text-dash-title text-ink">{pct(latest?.pass)}</p>
          <p className="mt-4 text-data text-ink-muted tabular-nums">
            {latest?.band ? `95% CI ${pct(latest.band[0])}–${pct(latest.band[1])}` : latest ? "No interval" : "No completed run yet"}
          </p>
        </Tile>
        <Tile label="Baseline" testId="overview-baseline">
          {baseline ? (
            <>
              <p className="font-display text-dash-heading text-ink">{pct(baselineRate)}</p>
              <p className="mt-4 text-data text-ink-muted">
                <Link
                  href={`/projects/${projectId}/runs/${baseline.run_id}`}
                  className="rounded-xs text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
                >
                  {baseline.branch} baseline
                </Link>
                {latest?.pass != null && baselineRate != null && latest.id !== baseline.run_id && (
                  <> · latest {signed(latest.pass - baselineRate)}</>
                )}
              </p>
            </>
          ) : (
            <p className="text-body-sm text-ink-muted">
              None set for this suite. Set one from a completed run&apos;s page, and later runs are compared against it.
            </p>
          )}
        </Tile>
        <Tile label="Last run">
          <p className="font-display text-dash-heading text-ink">{suiteRuns[0] ? date(suiteRuns[0].created_at) : "—"}</p>
          <p className="mt-4 text-data text-ink-muted">
            {suiteRuns.length} {suiteRuns.length === 1 ? "run" : "runs"} of this suite in total
          </p>
        </Tile>
      </div>

      <div className="mt-12 grid grid-cols-1 gap-12 desktop:grid-cols-2">
        <div className="desktop:col-span-2">
          <PassRateChart points={points} baseline={baseline && baselineRate != null ? { rate: baselineRate, branch: baseline.branch } : null} />
        </div>
        <CostChart points={points} />
        <LatencyChart points={points} />
      </div>

      <Card
        title="Latest runs"
        className="mt-20"
        actions={
          <Link
            href={`/projects/${projectId}/runs`}
            className="rounded-xs text-body-sm text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
          >
            All runs
          </Link>
        }
      >
        <RunsTable runs={data.runs.slice(0, LATEST)} projectId={projectId} baselines={branches} caption="Latest runs, all suites" />
      </Card>
      {runDialog}
    </>
  );
}

const signed = (delta: number) => `${delta > 0 ? "+" : delta < 0 ? "−" : "±"}${pct(Math.abs(delta))}`;

function Tile({ label, testId, children }: { label: string; testId?: string; children: ReactNode }) {
  return (
    <section aria-label={label} data-testid={testId} className="min-w-0 rounded-xl bg-surface-1 p-20">
      <h2 className="mb-8 text-data-label text-ink-muted">{label}</h2>
      {children}
    </section>
  );
}
