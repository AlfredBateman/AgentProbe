"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RunSuiteDialog } from "@/components/run/run-suite-dialog";
import { RunsTable } from "@/components/run/runs-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Label, Select } from "@/components/ui/field";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { type Baseline, baselineBranches, type RunRow } from "@/lib/trends";

type Suite = components["schemas"]["SuiteOut"];
const PAGE = 50;

/** Every run in the project, newest first, filterable by suite and paged with "Load more" (E2). */
export default function RunsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [suiteId, setSuiteId] = useState("");
  const [runs, setRuns] = useState<RunRow[] | "loading" | "error">("loading");
  const [more, setMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [baselines, setBaselines] = useState<Baseline[]>([]);
  const [dialog, setDialog] = useState(false);

  const fetchPage = useCallback(
    (offset: number) =>
      api.GET("/projects/{project_id}/runs", {
        params: { path: { project_id: projectId }, query: { limit: PAGE, offset, ...(suiteId ? { suite_id: suiteId } : {}) } },
      }),
    [projectId, suiteId],
  );

  useEffect(() => {
    const path = { project_id: projectId };
    api.GET("/projects/{project_id}/suites", { params: { path } }).then(({ data }) => setSuites(data ?? []));
    api.GET("/projects/{project_id}/baselines", { params: { path } }).then(({ data }) => setBaselines(data ?? []));
  }, [projectId]);

  useEffect(() => {
    let current = true; // a suite picked while the previous page loads must not be overwritten by it
    fetchPage(0).then(({ data }) => {
      if (!current) return;
      setRuns(data ?? "error");
      setMore(data?.length === PAGE);
    });
    return () => {
      current = false;
    };
  }, [fetchPage]);

  async function loadMore() {
    if (!Array.isArray(runs)) return;
    setLoadingMore(true);
    const { data } = await fetchPage(runs.length);
    setLoadingMore(false);
    if (data) {
      // Runs started since the first page shift the offsets; drop the repeats that causes.
      const seen = new Set(runs.map((r) => r.id));
      setRuns([...runs, ...data.filter((r) => !seen.has(r.id))]);
      setMore(data.length === PAGE);
    }
  }

  const branches = useMemo(() => baselineBranches(baselines), [baselines]);

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-12">
        <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Runs</h1>
        <Button data-testid="run-a-suite" onClick={() => setDialog(true)}>
          Run a suite
        </Button>
      </header>
      <div className="mt-20 flex flex-wrap items-center gap-12">
        <Label htmlFor="runs-suite">Suite</Label>
        <Select
          id="runs-suite"
          data-testid="runs-suite"
          value={suiteId}
          onChange={(e) => {
            setRuns("loading");
            setSuiteId(e.target.value);
          }}
          className="min-w-200"
        >
          <option value="">All suites</option>
          {suites.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
      </div>
      <Card className="mt-15">
        {runs === "loading" && <Skeleton className="h-120" />}
        {runs === "error" && <EmptyState title="Couldn't load runs" description="Check your connection and reload the page." />}
        {Array.isArray(runs) && (
          <>
            <RunsTable runs={runs} projectId={projectId} baselines={branches} caption="Runs" />
            {more && (
              <div className="mt-15 flex justify-center">
                <Button variant="secondary" onClick={() => void loadMore()} disabled={loadingMore}>
                  {loadingMore ? "Loading…" : "Load more"}
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
      {dialog && <RunSuiteDialog projectId={projectId} suites={suites} suiteId={suiteId || undefined} onClose={() => setDialog(false)} />}
    </>
  );
}
