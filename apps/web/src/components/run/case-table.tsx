"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input, Label, Select } from "@/components/ui/field";
import { StatusDot } from "@/components/ui/status";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { ms, score, usd } from "@/lib/format";
import { type CaseRow, filterRows, type Filters, NO_FILTERS } from "@/lib/run-cases";
import { AttemptBadge, JudgmentBadge, LABELS, LabelBadge } from "./labels";

type Result = components["schemas"]["ResultOut"];

type Props = {
  rows: CaseRow[];
  runId: string;
  projectId: string;
  runsPerCase: number;
  /** Changes whenever attempts arrive, so an open row refetches its detail. */
  version: string;
};

const DOT = { passed: "pass", failed: "fail", error: "error" } as const;

export function CaseTable({ rows, runId, projectId, runsPerCase, version }: Props) {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const categories = [...new Set(rows.map((r) => r.attackCategory).filter((c): c is string => !!c))].sort();
  const shown = filterRows(rows, filters);
  const set = (key: keyof Filters) => (e: { target: { value: string } }) => setFilters({ ...filters, [key]: e.target.value });

  const columns: Column<CaseRow>[] = [
    { key: "case", header: "Case", value: (r) => r.case, render: (r) => <span className="font-mono text-code">{r.case}</span> },
    {
      key: "label",
      header: "Stability",
      value: (r) => r.label,
      render: (r) => (r.label ? <LabelBadge label={r.label} /> : <span className="text-ink-muted">Pending</span>),
    },
    {
      key: "passes",
      header: "Passes",
      value: (r) => (r.done ? r.passes / r.done : null),
      align: "right",
      render: (r) => (
        <span className="inline-flex items-center gap-8">
          {/* One mark per attempt; below 1199px the table is too narrow for it. */}
          <span aria-hidden className="hidden gap-3 desktop:inline-flex">
            {r.attempts.map((a) => (
              <StatusDot key={a.attempt} status={DOT[a.status as keyof typeof DOT] ?? "error"} decorative />
            ))}
          </span>
          {r.passes}/{r.done}
          {!r.label && r.done < runsPerCase && <span className="text-ink-muted">of {runsPerCase}</span>}
        </span>
      ),
    },
    { key: "score", header: "Score", value: (r) => r.meanScore, align: "right", render: (r) => score(r.meanScore) },
    { key: "consistency", header: "Consistency", value: (r) => r.consistency, align: "right", render: (r) => score(r.consistency) },
    { key: "latency", header: "Latency", value: (r) => r.meanLatencyMs, align: "right", render: (r) => ms(r.meanLatencyMs) },
    { key: "cost", header: "Cost", value: (r) => r.totalCost, align: "right", render: (r) => usd(r.totalCost) },
  ];

  return (
    <>
      <div role="search" aria-label="Filter cases" className="mb-15 grid grid-cols-2 gap-12 tablet:grid-cols-4">
        <div className="col-span-2 flex flex-col gap-6 tablet:col-span-1">
          <Label htmlFor="case-search">Search</Label>
          <Input id="case-search" type="search" placeholder="Case id" value={filters.q} onChange={set("q")} />
        </div>
        <div className="flex flex-col gap-6">
          <Label htmlFor="case-status">Attempt status</Label>
          <Select id="case-status" value={filters.status} onChange={set("status")}>
            <option value="">Any</option>
            <option value="passed">Has a pass</option>
            <option value="failed">Has a failure</option>
            <option value="error">Has an error</option>
          </Select>
        </div>
        <div className="flex flex-col gap-6">
          <Label htmlFor="case-label">Stability</Label>
          <Select id="case-label" value={filters.label} onChange={set("label")}>
            <option value="">Any</option>
            {LABELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.text}
              </option>
            ))}
          </Select>
        </div>
        <div className="col-span-2 flex flex-col gap-6 tablet:col-span-1">
          <Label htmlFor="case-category">Attack category</Label>
          <Select id="case-category" value={filters.category} onChange={set("category")}>
            <option value="">Any</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <p aria-live="polite" className="mb-8 text-data-label text-ink-muted">
        {shown.length === rows.length ? `${rows.length} ${rows.length === 1 ? "case" : "cases"}` : `${shown.length} of ${rows.length} cases`}
      </p>
      <DataTable
        caption="Cases"
        columns={columns}
        rows={shown}
        rowKey={(r) => r.case}
        expand={(r) => <CaseAttempts runId={runId} projectId={projectId} caseId={r.case} version={version} />}
        expandLabel={(r) => `attempts of ${r.case}`}
        empty={
          <EmptyState
            title={rows.length ? "No cases match" : "No attempts yet"}
            description={rows.length ? "Clear a filter to see more." : "Cases appear here as their attempts finish."}
          />
        }
      />
    </>
  );
}

/** One case's attempts with every judge's reason, fetched when the row opens. */
function CaseAttempts({ runId, projectId, caseId, version }: { runId: string; projectId: string; caseId: string; version: string }) {
  const [results, setResults] = useState<Result[] | "loading" | "error">("loading");

  useEffect(() => {
    api
      .GET("/runs/{run_id}/results", { params: { path: { run_id: runId }, query: { case: caseId } } })
      .then(({ data }) => setResults(data ?? "error"));
  }, [runId, caseId, version]);

  if (results === "loading") return <Skeleton className="h-60" />;
  if (results === "error") return <p className="text-body-sm text-ink-muted">Couldn&rsquo;t load the attempts.</p>;
  return (
    <ol className="flex flex-col gap-12 whitespace-normal" aria-label={`Attempts of ${caseId}`}>
      {results.map((r) => (
        <li key={r.id} className="rounded-lg bg-canvas p-12">
          <div className="flex flex-wrap items-center gap-x-12 gap-y-6 text-data tabular-nums">
            <span className="font-medium text-ink">Attempt {r.attempt + 1}</span>
            <AttemptBadge status={r.status} />
            <span className="text-ink-muted">Score {score(r.score)}</span>
            <span className="text-ink-muted">{ms(r.latency_ms)}</span>
            <span className="text-ink-muted">{usd(r.cost)}</span>
            {r.error_kind && <span className="text-ink-muted">{r.error_kind} error</span>}
            <Link
              href={`/projects/${projectId}/runs/${runId}/results/${r.id}`}
              className="ml-auto rounded-xs text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
            >
              View trace
            </Link>
          </div>
          {r.judgments.length > 0 && (
            <ul className="mt-8 flex flex-col gap-6">
              {r.judgments.map((j, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-8 gap-y-4 text-body-sm">
                  <JudgmentBadge status={j.status} />
                  <span className="font-mono text-code text-ink">{j.judge}</span>
                  {/* Judge reasons quote agent output: plain text only. */}
                  <span className="min-w-0 break-words text-ink-muted">{j.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}
