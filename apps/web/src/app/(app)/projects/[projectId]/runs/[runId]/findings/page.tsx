"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AttemptBadge } from "@/components/run/labels";
import { Card } from "@/components/ui/card";
import { PlainText } from "@/components/ui/code";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { GradientCard } from "@/components/ui/gradient-card";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { count } from "@/lib/format";

type Finding = components["schemas"]["FindingOut"];
type Result = components["schemas"]["ResultOut"];

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

  return (
    <>
      <p className="text-data-label text-ink-muted">
        <Link href={`/projects/${projectId}/runs/${runId}`} className="rounded-xs outline-none hover:text-ink focus-visible:shadow-focus">
          Run <span className="font-mono">{runId.slice(0, 8)}</span>
        </Link>{" "}
        / Findings
      </p>
      <h1 className="mt-4 font-display text-dash-title-sm break-words tablet:text-dash-title">Findings</h1>

      {findings === "loading" && <Skeleton className="mt-20 h-320" />}
      {findings === "error" && (
        <div className="mt-20">
          <EmptyState title="Couldn't load findings" description="Check your connection and reload the page." />
        </div>
      )}
      {Array.isArray(findings) && findings.length === 0 && (
        <div className="mt-20">
          <EmptyState
            title="No repeating failures"
            description="Findings group similar failing outputs into likely root causes; this run has none to group, or hasn't finished yet."
          />
        </div>
      )}
      {Array.isArray(findings) && findings.length > 0 && (
        <>
          <GradientCard className="mt-20">
            <p className="text-data-label text-ink/80">Root-cause clustering</p>
            <p className="mt-4 font-display text-dash-title">
              {count(findings.reduce((n, f) => n + f.member_result_ids.length, 0))} failing attempts → {count(findings.length)}{" "}
              {findings.length === 1 ? "finding" : "findings"}
            </p>
          </GradientCard>

          <div className="mt-20 flex flex-col gap-15">
            {findings.map((f) => (
              <FindingCard key={f.id} finding={f} results={results} projectId={projectId} runId={runId} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

function FindingCard({
  finding,
  results,
  projectId,
  runId,
}: {
  finding: Finding;
  results: Map<string, Result>;
  projectId: string;
  runId: string;
}) {
  return (
    <Card
      title={finding.cluster_label}
      actions={<span className="text-data text-ink-muted">{finding.member_result_ids.length} failing attempts</span>}
    >
      <p className="text-body text-ink">{finding.summary}</p>
      {finding.suggested_fix && (
        <p className="mt-8 text-body-sm text-ink-muted">
          <span className="font-medium text-ink">Suggested fix:</span> {finding.suggested_fix}
        </p>
      )}
      <details className="group mt-12">
        <summary className="cursor-pointer list-none rounded-xs text-data-label text-accent-blue outline-none hover:underline focus-visible:shadow-focus [&::-webkit-details-marker]:hidden">
          <span className="group-open:hidden">Show {finding.member_result_ids.length} members</span>
          <span className="hidden group-open:inline">Hide members</span>
        </summary>
        <ol className="mt-8 flex flex-col gap-8" aria-label={`Members of ${finding.cluster_label}`}>
          {finding.member_result_ids.map((id) => {
            const r = results.get(id);
            return (
              <li key={id} className="rounded-lg bg-canvas p-12">
                <div className="flex flex-wrap items-center gap-x-12 gap-y-6 text-data">
                  <span className="font-mono text-code text-ink">{r?.case ?? id.slice(0, 8)}</span>
                  {r && <AttemptBadge status={r.status} />}
                  {r && <span className="text-ink-muted">Attempt {r.attempt + 1}</span>}
                  <Link
                    href={`/projects/${projectId}/runs/${runId}/results/${id}`}
                    className="ml-auto rounded-xs text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
                  >
                    View trace
                  </Link>
                </div>
                {r?.output && <PlainText text={r.output} limit={400} className="mt-8" />}
              </li>
            );
          })}
        </ol>
      </details>
    </Card>
  );
}
