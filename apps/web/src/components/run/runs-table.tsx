import Link from "next/link";
import type { ReactNode } from "react";
import { RunStatusBadge } from "@/components/run/labels";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/feedback";
import { Badge } from "@/components/ui/status";
import { ms, pct, usd } from "@/lib/format";
import type { RunRow } from "@/lib/trends";

type Props = {
  runs: RunRow[];
  projectId: string;
  /** Run id -> branches it is the baseline of (`baselineBranches`). */
  baselines: ReadonlyMap<string, string[]>;
  caption: string;
  empty?: ReactNode;
};

const started = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
// Cost and latency are also on the trend charts and the run page; below desktop width the table
// drops them so it fits its card at 810px (ADR 0028 §8 allows a table to scroll only below that).
const WIDE_ONLY = "hidden desktop:table-cell";

/** A project's runs, newest first: the overview's latest runs and the Runs page (E2). */
export function RunsTable({ runs, projectId, baselines, caption, empty }: Props) {
  const columns: Column<RunRow>[] = [
    {
      key: "suite",
      header: "Suite / agent",
      value: (r) => r.suite_name,
      render: (r) => (
        <span className="flex flex-col">
          <Link
            href={`/projects/${projectId}/runs/${r.id}`}
            className="self-start rounded-xs font-mono text-code text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
          >
            {r.suite_name}
          </Link>
          <span className="text-ink-muted">{r.agent_name ?? "—"}</span>
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      value: (r) => r.status,
      render: (r) => (
        <span className="flex flex-col items-start gap-4">
          <RunStatusBadge status={r.status} />
          {baselines.get(r.id)?.map((branch) => (
            <Badge key={branch} status="stable">{`Baseline · ${branch}`}</Badge>
          ))}
        </span>
      ),
    },
    {
      key: "branch",
      header: "Branch",
      value: (r) => r.branch ?? "",
      render: (r) => (
        <span className="block max-w-160 truncate" title={r.branch ?? undefined}>
          {r.branch ?? "—"}
        </span>
      ),
    },
    {
      key: "pass_rate",
      header: "Pass rate",
      align: "right",
      value: (r) => r.pass_rate,
      render: (r) => (
        <span className="flex flex-col">
          {pct(r.pass_rate)}
          {r.ci_lower != null && r.ci_upper != null && (
            <span className="text-ink-muted">
              {pct(r.ci_lower, 0)}–{pct(r.ci_upper, 0)}
            </span>
          )}
        </span>
      ),
    },
    { key: "cost", header: "Cost", align: "right", value: (r) => r.total_cost, render: (r) => usd(r.total_cost), className: WIDE_ONLY },
    {
      key: "latency",
      header: "Mean latency",
      align: "right",
      value: (r) => r.mean_latency_ms,
      render: (r) => ms(r.mean_latency_ms),
      className: WIDE_ONLY,
    },
    { key: "created_at", header: "Started", value: (r) => r.created_at, render: (r) => started.format(new Date(r.created_at)) },
  ];
  return (
    <DataTable
      caption={caption}
      columns={columns}
      rows={runs}
      rowKey={(r) => r.id}
      empty={empty ?? <EmptyState title="No runs yet" description="Start one from a suite, or push one from CI." />}
    />
  );
}
