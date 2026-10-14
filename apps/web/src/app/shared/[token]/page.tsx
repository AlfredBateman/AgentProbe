"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AttemptList } from "@/components/run/attempts";
import { LabelBadge, RunStatusBadge } from "@/components/run/labels";
import { BareHeader } from "@/components/shell/bare-header";
import { PageHeader } from "@/components/shell/page-header";
import { AsciiFrame } from "@/components/ui/ascii";
import { buttonClasses } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Panel } from "@/components/ui/panel";
import { Stat, StatGrid } from "@/components/ui/stat";
import { AttemptStrip, Bars, ChartFigure, ChartTable, RateWhiskers } from "@/components/ui/telemetry";
import type { components } from "@/lib/api/schema";
import { awakeFetch } from "@/lib/api/wake";
import { count, date, pct } from "@/lib/format";

type Shared = components["schemas"]["SharedRunOut"];
type SharedCase = Shared["cases"][number];

/**
 * A run's public, read-only snapshot: no account, no agent config, no raw trace (ADR 0018).
 * Everything on it came from an agent, a judge or a suite author, so it is all text children:
 * never HTML, never a link built from the data.
 */
export default function SharedRunPage() {
  const { token } = useParams<{ token: string }>();
  const [run, setRun] = useState<Shared | "loading" | "missing">("loading");

  useEffect(() => {
    // No session to refresh, but a shared link is often the first visit in a while: wait for a
    // sleeping API to wake (ADR 0036).
    awakeFetch(new Request(new URL(`/api/shared/${encodeURIComponent(token)}`, window.location.origin)))
      .then(async (r): Promise<Shared | "missing"> => (r.ok ? ((await r.json()) as Shared) : "missing"))
      .then(setRun, () => setRun("missing"));
  }, [token]);

  return (
    <div className="flex min-h-dvh flex-col">
      <BareHeader
        chipFromTablet
        right={
          <a href="/register" className={buttonClasses("secondary")}>
            Try AgentProbe
          </a>
        }
      />
      {typeof run === "object" && <SnapshotStrip run={run} />}
      <main className="mx-auto w-full max-w-1440 flex-1 px-16 py-32 tablet:px-32">
        {run === "loading" && <Skeleton className="h-320" />}
        {run === "missing" && <EmptyState title="This link doesn't work" description="It may have expired, or its owner revoked it." />}
        {typeof run === "object" && <SharedRun run={run} />}
      </main>
      <footer className="border-t border-hairline-strong px-16 py-16 tablet:px-32">
        <p className="mx-auto max-w-1440 type-micro text-ink-muted">
          AgentProbe<span aria-hidden>®</span> <span aria-hidden>{"///"}</span> A frozen copy of one run. Nothing on this page can be changed.
        </p>
      </footer>
    </div>
  );
}

/** What this page is, before anything else on it: a copy, read only, with its date and its limits. */
function SnapshotStrip({ run }: { run: Shared }) {
  return (
    <div className="border-b border-hairline-strong bg-surface-1">
      <div className="mx-auto flex max-w-1440 flex-wrap items-center gap-x-16 gap-y-4 px-16 py-8 tablet:px-32">
        <AsciiFrame className="text-accent">Read-only snapshot</AsciiFrame>
        <span aria-hidden className="type-micro text-ink-muted">
          {"///"}
        </span>
        <span className="type-micro text-ink-muted">Captured {date(run.finished_at ?? run.created_at)}</span>
        <span className="type-micro text-ink-muted tablet:ml-auto">No account needed. Agent config, credentials and raw traces are not included.</span>
      </div>
    </div>
  );
}

function SharedRun({ run }: { run: Shared }) {
  const attempts = (c: SharedCase) => run.results.filter((r) => r.case === c.case);
  const errorsOf = (c: SharedCase) => attempts(c).filter((r) => r.status === "error").length;
  const outcome = (status: string) => run.results.filter((r) => r.status === status).length;
  const total = run.cases.reduce((n, c) => n + c.attempts, 0);
  const label = (l: string) => run.cases.filter((c) => c.label === l).length;
  const pass = label("stable-pass");
  const flaky = label("flaky");
  const fail = label("stable-fail");
  const share = (n: number) => pct(run.cases.length ? n / run.cases.length : null, 0);
  const failed = outcome("failed");
  const hasInterval = run.ci_lower != null && run.ci_upper != null;
  const interval = hasInterval ? `${pct(run.ci_lower)}–${pct(run.ci_upper)}` : "No interval";

  const columns: Column<SharedCase>[] = [
    { key: "case", header: "Case", value: (c) => c.case, render: (c) => <span className="type-code">{c.case}</span> },
    { key: "label", header: "Stability", value: (c) => c.label, render: (c) => <LabelBadge label={c.label} /> },
    {
      key: "passes",
      header: "Passes",
      value: (c) => c.pass_rate,
      align: "right",
      render: (c) => (
        <span className="inline-flex items-center gap-8">
          <span className="hidden max-w-132 desktop:inline-flex">
            <AttemptStrip passes={c.passes} attempts={c.attempts} errors={errorsOf(c)} tone="candidate" />
          </span>
          {c.passes}/{c.attempts}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            Shared run <span aria-hidden>{"///"}</span> {run.runs_per_case} attempts per case
          </>
        }
        title={run.suite}
        verbatim
      >
        <div className="flex flex-wrap items-center gap-x-20 gap-y-8 type-data">
          <RunStatusBadge status={run.status} />
          <span className="text-ink-muted">
            Agent <span className="type-code text-ink">{run.agent}</span>
          </span>
          <span className="text-ink-muted">
            Finished <span className="text-ink">{date(run.finished_at)}</span>
          </span>
        </div>
      </PageHeader>

      <StatGrid className="mt-24">
        <Stat label="Pass rate" value={pct(run.pass_rate)} note={hasInterval ? `95% CI ${interval}` : "No interval"} />
        <Stat label="Cases" value={count(run.cases.length)} note={`${pass} stable · ${flaky} flaky · ${fail} failing`} />
        <Stat label="Attempts" value={count(total)} note={`${count(outcome("passed"))} passed`} />
        <Stat
          label="Failed attempts"
          value={count(failed)}
          tone={failed > 0 ? "fail" : undefined}
          note={outcome("error") > 0 ? `and ${outcome("error")} errored` : "None errored"}
        />
      </StatGrid>

      <div className="mt-24 grid gap-16 desktop:grid-cols-2">
        <ChartFigure
          title="Pass rate, 95% interval"
          note="Scale 0 to 100%"
          table={<ChartTable caption="Pass rate of this run and its 95% interval" head={["Run", "Pass rate", "95% interval"]} rows={[["This run", pct(run.pass_rate), interval]]} />}
        >
          <RateWhiskers rows={[{ label: "This run", tone: "candidate", value: run.pass_rate, lower: run.ci_lower, upper: run.ci_upper }]} />
        </ChartFigure>
        <ChartFigure
          title="Cases by stability"
          note={`${run.cases.length} ${run.cases.length === 1 ? "case" : "cases"}`}
          table={
            <ChartTable
              caption="Number of cases in each stability class"
              head={["Stability", "Cases", "Share"]}
              rows={[
                ["Stable pass", pass, share(pass)],
                ["Flaky", flaky, share(flaky)],
                ["Stable fail", fail, share(fail)],
              ]}
            />
          }
        >
          <Bars
            max={Math.max(1, run.cases.length)}
            rows={[
              { key: "pass", label: <span className="uppercase">Stable pass</span>, value: pass, tone: "candidate", note: share(pass) },
              { key: "flaky", label: <span className="uppercase">Flaky</span>, value: flaky, tone: "flaky", note: share(flaky) },
              { key: "fail", label: <span className="uppercase">Stable fail</span>, value: fail, tone: "fail", note: share(fail) },
            ]}
          />
        </ChartFigure>
      </div>

      <Panel
        title="Cases"
        titleStyle="label"
        className="mt-24"
        actions={<span className="type-micro text-ink-muted tabular-nums">{run.cases.length}</span>}
      >
        <div className="-mx-16 -mt-16">
          <DataTable
            caption="Cases"
            columns={columns}
            rows={run.cases}
            rowKey={(c) => c.case}
            expandLabel={(c) => `attempts of ${c.case}`}
            expand={(c) => (
              <AttemptList
                label={`Attempts of ${c.case}`}
                items={attempts(c).map((r) => ({
                  key: `${r.case}:${r.attempt}`,
                  attempt: r.attempt,
                  status: r.status,
                  score: r.score,
                  errorKind: r.error_kind,
                  output: r.output,
                  judgments: r.judgments,
                }))}
              />
            )}
            empty={<EmptyState title="No cases were summarized" />}
          />
        </div>
      </Panel>
    </>
  );
}
