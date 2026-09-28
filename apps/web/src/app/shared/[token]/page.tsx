"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AttemptBadge, JudgmentBadge, LabelBadge, RunStatusBadge } from "@/components/run/labels";
import { BareHeader } from "@/components/shell/bare-header";
import { buttonClasses } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PlainText } from "@/components/ui/code";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import type { components } from "@/lib/api/schema";
import { date, pct, score } from "@/lib/format";

type Shared = components["schemas"]["SharedRunOut"];
type SharedCase = Shared["cases"][number];

/** A run's public, read-only view: no account, no agent config, no raw trace (ADR 0018). */
export default function SharedRunPage() {
  const { token } = useParams<{ token: string }>();
  const [run, setRun] = useState<Shared | "loading" | "missing">("loading");

  useEffect(() => {
    // A plain fetch: this page has no session to refresh.
    fetch(`/api/shared/${encodeURIComponent(token)}`)
      .then(async (r): Promise<Shared | "missing"> => (r.ok ? ((await r.json()) as Shared) : "missing"))
      .then(setRun, () => setRun("missing"));
  }, [token]);

  return (
    <div className="flex min-h-dvh flex-col">
      <BareHeader
        right={
          <a href="/register" className={buttonClasses("secondary")}>
            Try AgentProbe
          </a>
        }
      />
      <main className="mx-auto w-full max-w-1440 flex-1 px-16 py-30 tablet:px-30">
        {run === "loading" && <Skeleton className="h-320" />}
        {run === "missing" && (
          <EmptyState title="This link doesn't work" description="It may have expired, or its owner revoked it." />
        )}
        {typeof run === "object" && <SharedRun run={run} />}
      </main>
    </div>
  );
}

function SharedRun({ run }: { run: Shared }) {
  const columns: Column<SharedCase>[] = [
    { key: "case", header: "Case", value: (c) => c.case, render: (c) => <span className="font-mono text-code">{c.case}</span> },
    { key: "label", header: "Stability", value: (c) => c.label, render: (c) => <LabelBadge label={c.label} /> },
    { key: "passes", header: "Passes", value: (c) => c.pass_rate, align: "right", render: (c) => `${c.passes}/${c.attempts}` },
  ];

  return (
    <>
      <p className="text-data-label text-ink-muted">Shared run · read-only</p>
      <h1 className="mt-4 font-display text-dash-title-sm break-words tablet:text-dash-title">{run.suite}</h1>
      <div className="mt-8 flex flex-wrap items-center gap-x-20 gap-y-8 text-data">
        <RunStatusBadge status={run.status} />
        <span className="text-ink-muted">
          Agent <span className="text-ink">{run.agent}</span>
        </span>
        <span className="text-ink-muted">
          Finished <span className="text-ink">{date(run.finished_at)}</span>
        </span>
      </div>

      <section aria-label="Pass rate" className="mt-20 rounded-xl bg-surface-1 p-20">
        <h2 className="mb-8 text-data-label text-ink-muted">Pass rate</h2>
        <p className="font-display text-dash-title">{pct(run.pass_rate)}</p>
        <p className="mt-4 text-data text-ink-muted tabular-nums">
          {run.ci_lower != null && run.ci_upper != null ? `95% CI ${pct(run.ci_lower)}–${pct(run.ci_upper)} · ` : ""}
          {run.runs_per_case} attempts per case
        </p>
      </section>

      <Card title="Cases" className="mt-20">
        <DataTable
          caption="Cases"
          columns={columns}
          rows={run.cases}
          rowKey={(c) => c.case}
          expandLabel={(c) => `attempts of ${c.case}`}
          expand={(c) => (
            <ol className="flex flex-col gap-12 whitespace-normal">
              {run.results
                .filter((r) => r.case === c.case)
                .map((r) => (
                  <li key={r.attempt} className="rounded-lg bg-canvas p-12">
                    <div className="flex flex-wrap items-center gap-x-12 gap-y-6 text-data">
                      <span className="font-medium text-ink">Attempt {r.attempt + 1}</span>
                      <AttemptBadge status={r.status} />
                      <span className="text-ink-muted">Score {score(r.score)}</span>
                    </div>
                    {r.output && <PlainText text={r.output} limit={600} className="mt-8" />}
                    <ul className="mt-8 flex flex-col gap-6">
                      {r.judgments.map((j, i) => (
                        <li key={i} className="flex flex-wrap items-baseline gap-x-8 gap-y-4 text-body-sm">
                          <JudgmentBadge status={j.status} />
                          <span className="font-mono text-code text-ink">{j.judge}</span>
                          <span className="min-w-0 break-words text-ink-muted">{j.reason}</span>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
            </ol>
          )}
          empty={<EmptyState title="No cases were summarized" />}
        />
      </Card>
    </>
  );
}
