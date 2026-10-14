"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { RunButton } from "@/components/run/run-button";
import { RunSuiteDialog } from "@/components/run/run-suite-dialog";
import { RunsTable } from "@/components/run/runs-table";
import { PageHeader } from "@/components/shell/page-header";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input, Label, Select } from "@/components/ui/field";
import { Pagination } from "@/components/ui/pagination";
import { Panel } from "@/components/ui/panel";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useStagger } from "@/lib/motion/hooks";
import {
  apiQuery,
  type ApiStatus,
  fromTableSort,
  PAGE_SIZE,
  parseRunsQuery,
  RUN_STATUSES,
  rangeText,
  type RunsQuery,
  runsSearch,
  tableSort,
} from "@/lib/runs-query";
import { type Baseline, baselineBranches, type RunRow } from "@/lib/trends";

type Suite = components["schemas"]["SuiteOut"];
type Page = { runs: RunRow[]; total: number };

export default function RunsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-320" />}>
      <Runs />
    </Suspense>
  );
}

const STATUS_TEXT: Record<ApiStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** Every run in the project: filtered, sorted and paged by the API, with the view in the URL. */
function Runs() {
  const { projectId } = useParams<{ projectId: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const query = useMemo(() => parseRunsQuery(new URLSearchParams(params.toString())), [params]);
  const [page, setPage] = useState<Page | "loading" | "error">("loading");
  const [suites, setSuites] = useState<Suite[]>([]);
  const [baselines, setBaselines] = useState<Baseline[]>([]);
  const [dialog, setDialog] = useState(false);
  const [branch, setBranch] = useState(query.branch);
  const [urlBranch, setUrlBranch] = useState(query.branch);
  if (urlBranch !== query.branch) {
    // Back or a link changed the URL: the box follows it, so the effect below doesn't undo it.
    setUrlBranch(query.branch);
    setBranch(query.branch);
  }

  const go = (next: Partial<RunsQuery>) =>
    // Any change but paging goes back to the first page; the table's position is kept.
    router.replace(`${pathname}${runsSearch({ ...query, page: 1, ...next })}`, { scroll: false });

  useEffect(() => {
    const path = { project_id: projectId };
    api.GET("/projects/{project_id}/suites", { params: { path } }).then(({ data }) => setSuites(data ?? []));
    api.GET("/projects/{project_id}/baselines", { params: { path } }).then(({ data }) => setBaselines(data ?? []));
  }, [projectId]);

  useEffect(() => {
    let current = true; // a filter changed while the previous page loads must not be overwritten by it
    api
      .GET("/projects/{project_id}/runs", { params: { path: { project_id: projectId }, query: apiQuery(query) } })
      .then(({ data, response }) => {
        if (!current) return;
        setPage(data ? { runs: data, total: Number(response.headers.get("X-Total-Count") ?? data.length) } : "error");
      });
    return () => {
      current = false;
    };
  }, [projectId, query]);

  // The branch box filters as you type, a moment after the last key.
  useEffect(() => {
    if (branch === query.branch) return;
    const timer = setTimeout(() => go({ branch }), 300);
    return () => clearTimeout(timer);
  });

  const branches = useMemo(() => baselineBranches(baselines), [baselines]);
  const pageCount = typeof page === "object" ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const range = typeof page === "object" ? rangeText(query.page, page.runs.length, page.total) : null;
  const filtered = !!(query.suite || query.status || query.branch);

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            [ Project ] <span aria-hidden>{"///"}</span>{" "}
            {typeof page === "object"
              ? [page.total.toLocaleString(), filtered && "matching", page.total === 1 ? "run" : "runs"].filter(Boolean).join(" ")
              : "Loading"}
          </>
        }
        title="Runs"
        actions={<RunButton data-testid="run-a-suite" label="Run a suite" onClick={() => setDialog(true)} />}
      />

      <div role="search" aria-label="Filter runs" className="mt-24 grid-lines grid-cols-1 border border-hairline tablet:grid-cols-3">
        <div className="flex flex-col gap-6 p-12">
          <Label htmlFor="runs-suite">Suite</Label>
          <Select id="runs-suite" data-testid="runs-suite" value={query.suite} onChange={(e) => go({ suite: e.target.value })}>
            <option value="">All suites</option>
            {suites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-6 p-12">
          <Label htmlFor="runs-status">Status</Label>
          <Select
            id="runs-status"
            data-testid="runs-status"
            value={query.status}
            onChange={(e) => go({ status: e.target.value as ApiStatus | "" })}
          >
            <option value="">Any status</option>
            {RUN_STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_TEXT[s]}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-6 p-12">
          <Label htmlFor="runs-branch">Branch</Label>
          <Input
            id="runs-branch"
            data-testid="runs-branch"
            type="search"
            placeholder="Exact name, e.g. main"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
        </div>
      </div>

      <Panel
        className="mt-24"
        title="Runs"
        titleStyle="label"
        actions={
          <p aria-live="polite" className="type-micro text-ink-muted tabular-nums">
            {range ?? (page === "loading" ? "Loading" : "")}
          </p>
        }
      >
        {page === "loading" && <Skeleton className="h-120" />}
        {page === "error" && <EmptyState title="Couldn't load runs" description="Check your connection and reload the page." />}
        {typeof page === "object" && (
          <Table
            page={page}
            query={query}
            projectId={projectId}
            branches={branches}
            filtered={filtered}
            onSort={(s) => go(fromTableSort(s))}
          />
        )}
        {typeof page === "object" && pageCount > 1 && (
          <Pagination
            className="mt-16"
            label="Runs pages"
            page={query.page}
            pageCount={pageCount}
            onPageChange={(p) => go({ page: p })}
          />
        )}
      </Panel>
      {dialog && (
        <RunSuiteDialog projectId={projectId} suites={suites} suiteId={query.suite || undefined} onClose={() => setDialog(false)} />
      )}
    </>
  );
}

function Table({
  page,
  query,
  projectId,
  branches,
  filtered,
  onSort,
}: {
  page: Page;
  query: RunsQuery;
  projectId: string;
  branches: ReadonlyMap<string, string[]>;
  filtered: boolean;
  onSort: Parameters<typeof RunsTable>[0]["onSortChange"];
}) {
  const ref = useRef<HTMLDivElement>(null);
  useStagger(ref, "tbody tr");
  return (
    <div ref={ref} className="-mx-16 -mb-16">
      <RunsTable
        runs={page.runs}
        projectId={projectId}
        baselines={branches}
        caption="Runs"
        sort={tableSort(query)}
        onSortChange={onSort}
        empty={
          filtered ? (
            <EmptyState title="No runs match" description="Clear a filter to see more." />
          ) : undefined
        }
      />
    </div>
  );
}
