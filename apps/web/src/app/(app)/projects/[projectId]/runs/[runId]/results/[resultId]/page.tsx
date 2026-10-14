"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, useEffect, useState } from "react";
import { AttemptBadge } from "@/components/run/labels";
import { PageHeader } from "@/components/shell/page-header";
import { differingSteps, type Trace, Timeline, VerdictPanel } from "@/components/trace/timeline";
import { CodeBlock, CopyButton, PlainText, safeJson } from "@/components/ui/code";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Label, Select } from "@/components/ui/field";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { cx } from "@/lib/cx";
import { count, date, ms, usd } from "@/lib/format";

type Result = components["schemas"]["ResultOut"];
type RunListItem = components["schemas"]["RunListOut"];

const LONG_TRACE = 30;

export default function TracePage() {
  return (
    <Suspense fallback={<Skeleton className="h-320" />}>
      <TraceView />
    </Suspense>
  );
}

function useTrace(resultId: string | null) {
  const [trace, setTrace] = useState<{ id: string; trace: Trace | "error" } | null>(null);
  useEffect(() => {
    if (!resultId) return;
    api
      .GET("/results/{result_id}/trace", { params: { path: { result_id: resultId } } })
      .then(({ data }) => setTrace({ id: resultId, trace: data ?? "error" }));
  }, [resultId]);
  return resultId && trace?.id === resultId ? trace.trace : null;
}

function TraceView() {
  const { projectId, runId, resultId } = useParams<{ projectId: string; runId: string; resultId: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const compareId = useSearchParams().get("compare");
  const [compactChoice, setCompact] = useState<boolean | null>(null);
  const trace = useTrace(resultId);
  const other = useTrace(compareId);

  if (trace === null) return <Skeleton className="h-320" />;
  if (trace === "error") return <EmptyState title="Trace not found" description="It may belong to another project." />;
  const compact = compactChoice ?? trace.steps.length > LONG_TRACE; // long traces start compact

  const setCompare = (id: string | null) => router.replace(id ? `${pathname}?compare=${id}` : pathname, { scroll: false });
  const comparing = compareId !== null && other !== null && other !== "error" ? other : null;

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            [{" "}
            <Link href={`/projects/${projectId}/runs/${runId}`} className="hover:text-ink">
              Run <span className="type-code">{runId.slice(0, 8)}</span>
            </Link>{" "}
            ] <span aria-hidden>{"///"}</span> Attempt {trace.attempt + 1}
          </>
        }
        title={trace.case}
        verbatim
        actions={
          <span className="inline-flex items-center gap-8 border border-hairline-strong py-2 pr-2 pl-12 type-label text-ink-muted">
            Trace JSON
            <CopyButton text={safeJson(trace)} name="the trace as JSON" />
          </span>
        }
      >
        <AttemptMeta trace={trace} />
      </PageHeader>

      <div className={cx("mt-24 grid gap-24", compareId === null && "desktop:grid-cols-[minmax(0,1fr)_minmax(0,380px)]")}>
        <div className="flex min-w-0 flex-col gap-24">
          <CodeBlock as="kbd" label="Input" code={trace.input} />
          {trace.error && (
            <div role="alert" className="border border-fail p-16">
              <p className="mb-6 type-label text-fail">Error</p>
              <PlainText text={trace.error} />
            </div>
          )}

          <div className="flex flex-wrap items-end justify-between gap-12">
            <div role="group" aria-label="Step density" className="inline-flex border border-hairline-strong">
              {[
                { value: false, label: "Expanded" },
                { value: true, label: "Compact" },
              ].map((o) => (
                <button
                  key={o.label}
                  type="button"
                  aria-pressed={compact === o.value}
                  onClick={() => setCompact(o.value)}
                  className={cx(
                    "min-h-40 cursor-pointer px-16 type-button -outline-offset-2 transition-[background-color,color] duration-120 pointer-coarse:min-h-44",
                    compact === o.value ? "bracketed bg-surface-2 text-accent" : "text-ink-muted hover:text-ink",
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
            <ComparePicker projectId={projectId} runId={runId} resultId={resultId} trace={trace} value={compareId} onChange={setCompare} />
          </div>

          {compareId === null ? (
            <Timeline trace={trace} compact={compact} layout="narrow" />
          ) : comparing === null ? (
            other === "error" ? (
              <EmptyState title="Couldn't load the attempt to compare with" />
            ) : (
              <Skeleton className="h-320" />
            )
          ) : (
            <div className="grid gap-24 tablet:grid-cols-2">
              <CompareColumn name="A" trace={trace} compact={compact} against={comparing} />
              <CompareColumn name="B" trace={comparing} compact={compact} against={trace} />
            </div>
          )}
        </div>
        {compareId === null && (
          <aside aria-label="Verdicts" className="min-w-0 desktop:sticky desktop:top-80 desktop:self-start">
            <VerdictPanel trace={trace} />
          </aside>
        )}
      </div>
    </>
  );
}

function AttemptMeta({ trace, className }: { trace: Trace; className?: string }) {
  return (
    <div className={cx("flex flex-wrap items-center gap-x-20 gap-y-6 tabular-nums", className)}>
      <AttemptBadge status={trace.status} />
      {/* Only term/value groups inside the list: the badge is its own element beside it. */}
      <dl className="flex flex-wrap items-center gap-x-20 gap-y-6">
        <MetaItem term="Latency">{ms(trace.latency_ms)}</MetaItem>
        <MetaItem term="Tokens">{count(trace.tokens)}</MetaItem>
        <MetaItem term="Cost">{usd(trace.cost_usd)}</MetaItem>
        <MetaItem term="Judging">{usd(trace.judge_cost_usd)}</MetaItem>
        <MetaItem term="Retries">{trace.retries}</MetaItem>
      </dl>
    </div>
  );
}

function MetaItem({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline gap-6">
      <dt className="type-micro text-ink-muted">{term}</dt>
      <dd className="type-data text-ink">{children}</dd>
    </div>
  );
}

function CompareColumn({ name, trace, compact, against }: { name: string; trace: Trace; compact: boolean; against: Trace }) {
  const differs = differingSteps(trace.steps, against.steps);
  return (
    <section aria-label={`Attempt ${name}`} className="min-w-0">
      <header className="mb-12 border border-hairline-strong p-16">
        <h2 className="type-headline">
          {name} · run <span className="type-code">{trace.run_id.slice(0, 8)}</span>, attempt {trace.attempt + 1}
        </h2>
        <AttemptMeta trace={trace} className="mt-8" />
        <p className="mt-8 type-micro text-ink-muted">
          {differs.size === 0 ? "Every step matches." : `${differs.size} of ${trace.steps.length} steps differ.`}
        </p>
      </header>
      <Timeline trace={trace} compact={compact} layout="narrow" differs={differs} idPrefix={`step-${name}`} />
    </section>
  );
}

/** Other attempts of this case in this run, or the same case in another run of the suite. */
function ComparePicker({
  projectId,
  runId,
  resultId,
  trace,
  value,
  onChange,
}: {
  projectId: string;
  runId: string;
  resultId: string;
  trace: Trace;
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  const [siblings, setSiblings] = useState<Result[]>([]);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [picked, setPicked] = useState<{ run: string; result: string } | null>(null);

  useEffect(() => {
    const path = { run_id: runId };
    api.GET("/runs/{run_id}/results", { params: { path, query: { case: trace.case } } }).then(({ data }) => setSiblings(data ?? []));
    api.GET("/runs/{run_id}", { params: { path } }).then(async ({ data: run }) => {
      if (!run) return;
      const recent = await api.GET("/projects/{project_id}/runs", {
        params: { path: { project_id: projectId }, query: { suite_id: run.suite_id, limit: 20 } },
      });
      setRuns((recent.data ?? []).filter((r) => r.id !== runId && r.status === "completed"));
    });
  }, [projectId, runId, trace.case]);

  async function pickRun(otherRun: string) {
    // The same attempt number in the other run, or its first attempt of this case.
    const { data } = await api.GET("/runs/{run_id}/results", { params: { path: { run_id: otherRun }, query: { case: trace.case } } });
    const match = data?.find((r) => r.attempt === trace.attempt) ?? data?.[0];
    if (match) {
      setPicked({ run: otherRun, result: match.id });
      onChange(match.id);
    }
  }

  const selected = value === null ? "" : siblings.some((s) => s.id === value) ? `result:${value}` : picked ? `run:${picked.run}` : "";
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Label htmlFor="compare-with">Compare with</Label>
      <Select
        id="compare-with"
        className="min-w-240"
        value={selected}
        onChange={(e) => {
          const [kind, id] = e.target.value.split(":");
          if (!id) onChange(null);
          else if (kind === "result") onChange(id);
          else void pickRun(id);
        }}
      >
        <option value="">Nothing (single attempt)</option>
        <optgroup label="Attempts in this run">
          {siblings
            .filter((s) => s.id !== resultId)
            .map((s) => (
              <option key={s.id} value={`result:${s.id}`}>
                Attempt {s.attempt + 1} ({s.status})
              </option>
            ))}
        </optgroup>
        {runs.length > 0 && (
          <optgroup label="This case in another run">
            {runs.map((r) => (
              <option key={r.id} value={`run:${r.id}`}>
                {r.branch ? `${r.branch} · ` : ""}
                {date(r.created_at)} ({r.id.slice(0, 8)})
              </option>
            ))}
          </optgroup>
        )}
      </Select>
    </div>
  );
}
