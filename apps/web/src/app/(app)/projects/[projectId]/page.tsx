"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CountUp } from "@/components/landing/motion";
import { RunButton } from "@/components/run/run-button";
import { RunSuiteDialog } from "@/components/run/run-suite-dialog";
import { RunsTable } from "@/components/run/runs-table";
import { VerdictBadge } from "@/components/run/labels";
import { CostChart, LatencyChart, PassRateChart } from "@/components/run/trend-charts";
import { PageHeader } from "@/components/shell/page-header";
import { Button, buttonClasses } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Label, Select } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Stat, StatGrid } from "@/components/ui/stat";
import { Badge } from "@/components/ui/status";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { date, pct } from "@/lib/format";
import { useStagger } from "@/lib/motion/hooks";
import { type RegressionReportDump, verdictSummary } from "@/lib/regression";
import { type Baseline, baselineBranches, defaultSuite, type RunRow, suiteBaseline, trendPoints } from "@/lib/trends";

type Suite = components["schemas"]["SuiteOut"];
type CaseSummary = components["schemas"]["CaseSummaryOut"];
type Data = { runs: RunRow[]; baselines: Baseline[]; suites: Suite[] };
/** The latest completed run's own findings; null while they load. */
type Findings = {
  runId: string;
  cases: CaseSummary[] | null;
  /** "none": no baseline is set where this run would be compared (a 404). */
  verdict: components["schemas"]["RunVerdictOut"] | "none" | null;
};

// ponytail: the trends read the newest 200 runs; page through `offset` if a suite's history outgrows it.
const TREND_RUNS = 200;
const LATEST = 10;

const signed = (delta: number) => `${delta > 0 ? "+" : delta < 0 ? "−" : "±"}${pct(Math.abs(delta))}`;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** Project overview (E2): one suite's telemetry (pass rate against its baseline, flaky and
 * regressed cases, trends), the project's latest runs, and the quick ways to act. */
export default function ProjectOverview() {
  const { projectId } = useParams<{ projectId: string }>();
  const [data, setData] = useState<Data | "loading" | "error">("loading");
  const [suiteId, setSuiteId] = useState<string | null>(null);
  const [dialog, setDialog] = useState(false);
  const [findings, setFindings] = useState<Findings | null>(null);

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
  const latestId = points.at(-1)?.id ?? null;

  // The flakiness and regression panels read the latest completed run: its case summaries and its
  // verdict against the baseline. A newer selection replaces them; a stale answer is dropped.
  useEffect(() => {
    if (!latestId) return;
    let live = true;
    const path = { run_id: latestId };
    Promise.all([api.GET("/runs/{run_id}/cases", { params: { path } }), api.GET("/runs/{run_id}/verdict", { params: { path } })])
      .then(([cases, verdict]) => {
        if (!live) return;
        setFindings({ runId: latestId, cases: cases.data ?? [], verdict: verdict.data ?? (verdict.response.status === 404 ? "none" : null) });
      })
      .catch(() => live && setFindings({ runId: latestId, cases: null, verdict: null }));
    return () => {
      live = false;
    };
  }, [latestId]);

  const runDialog = dialog && loaded && (
    <RunSuiteDialog projectId={projectId} suites={loaded.suites} suiteId={selected ?? undefined} onClose={() => setDialog(false)} />
  );
  const header = (
    <PageHeader
      eyebrow={
        <>
          [ Project ] <span aria-hidden>{"///"}</span> Telemetry
        </>
      }
      title="Overview"
      actions={
        <RunButton
          data-testid="run-a-suite"
          onClick={() => setDialog(true)}
          blocked={!loaded ? "Loading the project." : loaded.suites.length === 0 ? "Add a suite to run first." : null}
          note={false}
        />
      }
    />
  );

  if (data === "loading")
    return (
      <>
        {header}
        <Skeleton className="mt-24 h-320" />
      </>
    );
  if (data === "error") return <EmptyState title="Couldn't load this project" description="Check your connection and reload the page." />;

  if (data.runs.length === 0)
    return (
      <>
        {header}
        <div className="mt-24 border border-hairline-strong">
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
                <Link href={`/projects/${projectId}/suites`} className={buttonClasses("secondary")}>
                  Go to Suites
                </Link>
              )
            }
          />
        </div>
        {runDialog}
      </>
    );

  const suite = data.suites.find((s) => s.id === selected);
  const suiteRuns = data.runs.filter((r) => r.suite_id === selected);
  const latest = points.at(-1);
  const baseline = selected ? suiteBaseline(data.baselines, selected) : null;
  const baselineRate = baseline?.run.pass_rate ?? null;
  const mine = findings?.runId === latestId ? findings : null;
  const verdict = mine && mine.verdict !== "none" ? mine.verdict : null;
  const report = (verdict?.report as RegressionReportDump | null | undefined) ?? null;
  const flaky = mine?.cases?.filter((c) => c.label === "flaky") ?? [];
  const regressed = report?.regressed.length ?? null;
  const summarized = !!mine?.cases?.length;

  return (
    <>
      {header}

      {/* The one filter row: the suite scopes the tiles, panels and charts below it. */}
      <div className="mt-24 flex flex-wrap items-center gap-x-12 gap-y-8">
        <Label htmlFor="overview-suite">Suite</Label>
        <Select id="overview-suite" data-testid="overview-suite" value={selected ?? ""} onChange={(e) => setSuiteId(e.target.value)} className="min-w-200">
          {/* Suites with runs, plus any without: runs can only be of a suite that exists. */}
          {data.suites.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
        <span className="type-micro text-ink-muted">
          {points.length} completed {points.length === 1 ? "run" : "runs"}
          {suite && ` · version ${suite.version}, ${plural(suite.case_count, "case")}`}
          {suiteRuns[0] && ` · last run ${date(suiteRuns[0].created_at)}`}
        </span>
      </div>

      <StatGrid className="mt-16">
        <Stat
          label="Latest pass rate"
          leader
          value={latest?.pass != null ? <CountUp value={pct(latest.pass)} /> : "—"}
          note={latest?.band ? `95% CI ${pct(latest.band[0])}–${pct(latest.band[1])}` : latest ? "No interval" : "No completed run yet"}
        />
        <div data-testid="overview-baseline">
          <Stat
            label="Baseline"
            leader
            value={baselineRate != null ? <CountUp value={pct(baselineRate)} /> : "—"}
            note={
              baseline ? (
                <>
                  <Link href={`/projects/${projectId}/runs/${baseline.run_id}`} className="text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-accent">
                    {baseline.branch} baseline
                  </Link>
                  {latest?.pass != null && baselineRate != null && latest.id !== baseline.run_id && <> {"///"} latest {signed(latest.pass - baselineRate)}</>}
                </>
              ) : (
                "None set for this suite"
              )
            }
          />
        </div>
        <Stat
          label="Flaky cases"
          leader
          value={summarized ? <CountUp value={String(flaky.length)} /> : "—"}
          note={summarized ? `of ${plural(mine.cases!.length, "case")} in the latest run` : "Not summarized yet"}
        />
        <Stat
          label="Regressed cases"
          leader
          tone={regressed ? "fail" : undefined}
          value={regressed !== null ? <CountUp value={String(regressed)} /> : "—"}
          note={
            report && verdict
              ? `against the ${verdict.branch} baseline`
              : verdict?.is_baseline
                ? "The latest run is the baseline"
                : mine?.verdict === "none"
                  ? "No baseline set"
                  : "Latest run's verdict"
          }
        />
      </StatGrid>

      {/* Flakiness, regression and the quick actions: three compartments of one row. */}
      <div className="mt-16 grid grid-cols-1 gap-16 desktop:grid-cols-3">
        <Panel aria-label="Flakiness" title="Flakiness" titleStyle="label" actions={<span className="type-micro text-ink-muted">Latest run</span>}>
          {!mine ? (
            <Skeleton className="h-80" />
          ) : mine.cases === null ? (
            <p className="type-body-sm text-ink-muted">Couldn&apos;t load this run&apos;s cases.</p>
          ) : mine.cases.length === 0 ? (
            <p className="type-body-sm text-ink-muted">Case summaries appear once a run has been summarized.</p>
          ) : flaky.length === 0 ? (
            <p className="type-body-sm text-ink">No case passed some attempts and failed others.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-hairline">
              {flaky.map((c) => (
                <li key={c.case} className="flex items-center justify-between gap-12 py-8 first:pt-0 last:pb-0">
                  <Link href={`/projects/${projectId}/runs/${mine.runId}`} className="min-w-0 truncate type-code text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-accent">
                    {c.case}
                  </Link>
                  <span className="flex shrink-0 items-center gap-8">
                    <span className="type-data tabular-nums text-ink-muted">
                      {c.passes}/{c.attempts}
                    </span>
                    <Badge status="flaky" />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel aria-label="Regression" title="Regression" titleStyle="label" actions={<span className="type-micro text-ink-muted">Against baseline</span>}>
          {!mine ? (
            <Skeleton className="h-80" />
          ) : mine.verdict === null ? (
            <p className="type-body-sm text-ink-muted">Couldn&apos;t load this run&apos;s verdict.</p>
          ) : mine.verdict === "none" ? (
            <p className="type-body-sm text-ink-muted">No baseline is set for this suite. Set one from a completed run&apos;s page, and later runs are compared against it.</p>
          ) : mine.verdict.is_baseline ? (
            <p className="type-body-sm text-ink">The latest run is the {mine.verdict.branch} baseline, so there is nothing to compare it with.</p>
          ) : report ? (
            <div className="flex flex-col items-start gap-12">
              <VerdictBadge verdict={report.verdict} />
              <p className="type-body-sm text-ink-muted">{verdictSummary(report)}</p>
              <Link href={`/projects/${projectId}/runs/${mine.runId}/compare`} className="type-label text-accent underline-offset-4 hover:underline">
                Open the comparison
              </Link>
            </div>
          ) : (
            <p className="type-body-sm text-ink-muted">The verdict is not ready yet.</p>
          )}
        </Panel>

        <Panel aria-label="Quick actions" title="Quick actions" titleStyle="label">
          <div className="grid grid-cols-1 gap-8 tablet:grid-cols-2 desktop:grid-cols-1">
            <RunButton
              variant="secondary"
              label="Run a suite"
              onClick={() => setDialog(true)}
              blocked={data.suites.length === 0 ? "Add a suite to run first." : null}
              note={false}
              block
            />
            <Link href={`/projects/${projectId}/agents`} className={buttonClasses("secondary")}>
              Add an agent
            </Link>
            <Link href={`/projects/${projectId}/suites`} className={buttonClasses("secondary")}>
              New suite
            </Link>
            <Link href={`/projects/${projectId}/settings`} className={buttonClasses("secondary")}>
              Create an API key
            </Link>
          </div>
        </Panel>
      </div>

      <div className="mt-16 grid grid-cols-1 gap-16 desktop:grid-cols-2">
        <div className="desktop:col-span-2">
          <PassRateChart points={points} baseline={baseline && baselineRate != null ? { rate: baselineRate, branch: baseline.branch } : null} />
        </div>
        <CostChart points={points} />
        <LatencyChart points={points} />
      </div>

      <LatestRuns projectId={projectId} runs={data.runs.slice(0, LATEST)} baselines={branches} />
      {runDialog}
    </>
  );
}

function LatestRuns({ projectId, runs, baselines }: { projectId: string; runs: RunRow[]; baselines: ReadonlyMap<string, string[]> }) {
  const ref = useRef<HTMLDivElement>(null);
  useStagger(ref, "tbody tr");
  return (
    <Panel
      title="Latest runs"
      className="mt-16"
      actions={
        <Link href={`/projects/${projectId}/runs`} className="type-label text-accent underline-offset-4 hover:underline">
          All runs
        </Link>
      }
    >
      <div ref={ref}>
        <RunsTable runs={runs} projectId={projectId} baselines={baselines} caption="Latest runs, all suites" />
      </div>
    </Panel>
  );
}
