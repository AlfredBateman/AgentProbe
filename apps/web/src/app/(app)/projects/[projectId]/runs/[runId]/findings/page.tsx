"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AttemptList } from "@/components/run/attempts";
import { PageHeader } from "@/components/shell/page-header";
import { PlainText } from "@/components/ui/code";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Stat, StatGrid } from "@/components/ui/stat";
import { Bars, ChartFigure, ChartTable } from "@/components/ui/telemetry";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { count, pct } from "@/lib/format";

type Finding = components["schemas"]["FindingOut"];
type Result = components["schemas"]["ResultOut"];

const index = (i: number) => `F-${String(i + 1).padStart(2, "0")}`;

/** Failure clustering (ADR 0024): every failing attempt collapsed into "N failures -> K
 * findings", each a likely root cause with a suggested fix. Largest clusters first, as the
 * API already orders them. */
export default function FindingsPage() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>();
  const [findings, setFindings] = useState<Finding[] | "loading" | "error">("loading");
  const [results, setResults] = useState<Map<string, Result>>(new Map());

  useEffect(() => {
    const path = { run_id: runId };
    Promise.all([
      api.GET("/runs/{run_id}/findings", { params: { path } }),
      api.GET("/runs/{run_id}/results", { params: { path, query: { status: "failed" } } }),
    ]).then(([f, r]) => {
      setFindings(f.data ?? "error");
      setResults(new Map((r.data ?? []).map((row) => [row.id, row])));
    });
  }, [runId]);

  const list = Array.isArray(findings) ? findings : [];
  const failing = list.reduce((n, f) => n + f.member_result_ids.length, 0);
  const cases = new Set(list.flatMap((f) => f.member_result_ids.map((id) => results.get(id)?.case).filter((c): c is string => !!c)));

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            [{" "}
            <Link href={`/projects/${projectId}/runs/${runId}`} className="hover:text-ink">
              Run <span className="type-code">{runId.slice(0, 8)}</span>
            </Link>{" "}
            ] <span aria-hidden>{"///"}</span> Findings
          </>
        }
        title="Findings"
      >
        {list.length > 0 && (
          <p className="type-data text-ink-muted tabular-nums">
            {count(failing)} failing {failing === 1 ? "attempt" : "attempts"} → {count(list.length)} {list.length === 1 ? "finding" : "findings"}
          </p>
        )}
      </PageHeader>

      {findings === "loading" && <Skeleton className="mt-24 h-320" />}
      {findings === "error" && (
        <div className="mt-24">
          <EmptyState title="Couldn't load findings" description="Check your connection and reload the page." />
        </div>
      )}
      {Array.isArray(findings) && findings.length === 0 && (
        <div className="mt-24">
          <EmptyState
            title="No repeating failures"
            description="Findings group similar failing outputs into likely root causes; this run has none to group, or hasn't finished yet."
          />
        </div>
      )}
      {list.length > 0 && (
        <>
          <StatGrid className="mt-24">
            <Stat label="Failing attempts" value={count(failing)} tone="fail" note="Grouped by the likely cause of each" />
            <Stat label="Findings" value={count(list.length)} note="Likely root causes" />
            <Stat label="Largest finding" value={count(Math.max(...list.map((f) => f.member_result_ids.length)))} note="Failing attempts in F-01" />
            <Stat label="Cases affected" value={cases.size ? count(cases.size) : "—"} note={cases.size ? "At least one failing attempt each" : "Not known for errored attempts"} />
          </StatGrid>

          <ChartFigure
            className="mt-24"
            title="Failing attempts per finding"
            note={`${count(failing)} in all`}
            table={
              <ChartTable
                caption="Failing attempts in each finding"
                head={["Finding", "Label", "Failing attempts", "Share"]}
                rows={list.map((f, i) => [index(i), f.cluster_label, count(f.member_result_ids.length), pct(failing ? f.member_result_ids.length / failing : null)])}
              />
            }
          >
            <Bars rows={list.map((f, i) => ({ key: f.id, label: `${index(i)} ${f.cluster_label}`, value: f.member_result_ids.length, tone: "fail" }))} />
          </ChartFigure>

          <ol aria-label="Findings" className="mt-24 flex flex-col gap-16">
            {list.map((f, i) => (
              <li key={f.id}>
                <FindingPanel finding={f} position={i} results={results} projectId={projectId} runId={runId} />
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  );
}

function FindingPanel({
  finding,
  position,
  results,
  projectId,
  runId,
}: {
  finding: Finding;
  position: number;
  results: Map<string, Result>;
  projectId: string;
  runId: string;
}) {
  const members = finding.member_result_ids;
  const known = members.map((id) => results.get(id)).filter((r): r is Result => !!r);
  const unknown = members.filter((id) => !results.has(id));
  const traceHref = (id: string) => `/projects/${projectId}/runs/${runId}/results/${id}`;
  return (
    <article aria-labelledby={`finding-${finding.id}`} className="border border-hairline bg-canvas">
      <header className="flex flex-wrap items-baseline justify-between gap-x-12 gap-y-4 border-b border-hairline px-16 py-8">
        {/* The label is a model's words about agent output: plain text, never recased. */}
        <h2 id={`finding-${finding.id}`} className="min-w-0 type-body font-medium break-words">
          <span className="mr-8 type-micro text-ink-muted">{index(position)}</span>
          {finding.cluster_label}
        </h2>
        <p className="type-micro text-fail tabular-nums">
          {members.length} failing {members.length === 1 ? "attempt" : "attempts"}
        </p>
      </header>
      <div className="flex flex-col gap-12 p-16">
        <PlainText text={finding.summary} mono={false} limit={800} />
        {finding.suggested_fix && (
          <div className="border-l-2 border-hairline-strong pl-12">
            <p className="type-micro text-ink-muted">Suggested fix</p>
            <PlainText text={finding.suggested_fix} mono={false} limit={800} className="mt-2" />
          </div>
        )}
        <details className="group">
          <summary className="cursor-pointer list-none type-label text-accent hover:underline [&::-webkit-details-marker]:hidden">
            <span className="group-open:hidden">Show {members.length} members</span>
            <span className="hidden group-open:inline">Hide members</span>
          </summary>
          <div className="mt-12 flex flex-col gap-12">
            <AttemptList
              label={`Members of ${finding.cluster_label}`}
              items={known.map((r) => ({
                key: r.id,
                title: r.case,
                attempt: r.attempt,
                status: r.status,
                score: r.score,
                output: r.output,
                errorKind: r.error_kind,
                judgments: r.judgments,
                traceHref: traceHref(r.id),
              }))}
            />
            {unknown.length > 0 && (
              <ul aria-label="Members without a recorded result" className="flex flex-col gap-4">
                {unknown.map((id) => (
                  <li key={id} className="type-micro text-ink-muted">
                    <span className="type-code text-ink">{id.slice(0, 8)}</span>{" "}
                    <Link href={traceHref(id)} className="text-accent hover:underline">
                      View trace
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </details>
      </div>
    </article>
  );
}
