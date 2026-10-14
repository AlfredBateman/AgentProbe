import Link from "next/link";
import { PlainText } from "@/components/ui/code";
import { Skeleton } from "@/components/ui/feedback";
import { Panel } from "@/components/ui/panel";
import type { components } from "@/lib/api/schema";

type Finding = components["schemas"]["FindingOut"];
/** null: the run hasn't ended (clustering runs after it). */
export type Findings = Finding[] | "loading" | "error" | null;

const SHOWN = 4;

/**
 * The run's failure clusters (ADR 0024), largest first as the API orders them. A cluster's label,
 * summary and fix are a model's words about agent output: untrusted, shown as plain text only.
 */
export function FailureClusters({
  findings,
  caseOf,
  projectId,
  runId,
}: {
  findings: Findings;
  /** The case a failing attempt belongs to, from the attempts the page already has. */
  caseOf: (resultId: string) => string | undefined;
  projectId: string;
  runId: string;
}) {
  const all = `/projects/${projectId}/runs/${runId}/findings`;
  const failing = Array.isArray(findings) ? findings.reduce((n, f) => n + f.member_result_ids.length, 0) : 0;
  return (
    <Panel
      aria-label="Failure clusters"
      title="Failure clusters"
      titleStyle="label"
      actions={
        Array.isArray(findings) && findings.length > 0 ? (
          <p className="type-micro text-ink-muted tabular-nums">
            {failing} failing → {findings.length} {findings.length === 1 ? "cluster" : "clusters"}
          </p>
        ) : undefined
      }
    >
      {findings === null && <p className="type-body-sm text-ink-muted">Failing outputs are clustered when the run finishes.</p>}
      {findings === "loading" && <Skeleton className="h-60" />}
      {findings === "error" && <p className="type-body-sm text-ink-muted">Couldn&rsquo;t load the clusters.</p>}
      {Array.isArray(findings) && findings.length === 0 && (
        <p className="type-body-sm text-ink-muted">No failing outputs to group.</p>
      )}
      {Array.isArray(findings) && findings.length > 0 && (
        <ol aria-label="Failure clusters" className="-mx-16 -mt-16 flex flex-col">
          {findings.slice(0, SHOWN).map((f) => {
            const cases = [...new Set(f.member_result_ids.map(caseOf).filter((c): c is string => !!c))];
            return (
              <li key={f.id} className="border-t border-hairline px-16 py-12 first:border-t-0">
                <div className="flex flex-wrap items-baseline justify-between gap-x-12 gap-y-4">
                  <PlainText text={f.cluster_label} mono={false} limit={120} className="font-medium" />
                  <span className="type-micro text-fail tabular-nums">
                    {f.member_result_ids.length} {f.member_result_ids.length === 1 ? "attempt" : "attempts"}
                  </span>
                </div>
                <PlainText text={f.summary} mono={false} limit={400} className="mt-4 text-ink-muted" />
                {f.suggested_fix && (
                  <div className="mt-6 flex gap-8">
                    <span className="shrink-0 pt-2 type-micro text-ink-muted">Fix</span>
                    <PlainText text={f.suggested_fix} mono={false} limit={400} />
                  </div>
                )}
                <div className="mt-8 flex flex-wrap items-center gap-8">
                  {cases.map((c) => (
                    <span key={c} className="border border-hairline-strong px-6 py-2 type-code text-ink">
                      {c}
                    </span>
                  ))}
                  <Link
                    href={`/projects/${projectId}/runs/${runId}/results/${f.member_result_ids[0]}`}
                    className="tap ml-auto type-label text-accent underline-offset-4 hover:underline"
                  >
                    First trace
                  </Link>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {Array.isArray(findings) && findings.length > 0 && (
        <p className="-mx-16 border-t border-hairline px-16 pt-12 type-label">
          <Link href={all} className="tap text-accent underline-offset-4 hover:underline">
            {findings.length > SHOWN ? `All ${findings.length} clusters` : "Open findings"} {">>>"}
          </Link>
        </p>
      )}
    </Panel>
  );
}
