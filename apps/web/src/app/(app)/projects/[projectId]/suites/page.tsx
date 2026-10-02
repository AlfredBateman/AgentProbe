"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ChangeEvent, type FormEvent, useCallback, useEffect, useState } from "react";
import { RunSuiteDialog } from "@/components/run/run-suite-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, Label, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { date } from "@/lib/format";

type Suite = components["schemas"]["SuiteOut"];
type SuiteIssue = components["schemas"]["SuiteIssue"];

/** Suites (SPEC.md §9.5, E3): create one from YAML, open it (editor, cases, versions), run it. */
export default function SuitesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [suites, setSuites] = useState<Suite[] | "loading" | "error">("loading");
  const [createOpen, setCreateOpen] = useState(false);
  const [dialogKey, setDialogKey] = useState(0);
  const [running, setRunning] = useState<string | null>(null);

  const load = useCallback(() => {
    api.GET("/projects/{project_id}/suites", { params: { path: { project_id: projectId } } }).then(({ data }) =>
      setSuites(data ?? "error"),
    );
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<Suite>[] = [
    {
      key: "name",
      header: "Name",
      value: (s) => s.name,
      render: (s) => (
        <Link
          href={`/projects/${projectId}/suites/${s.id}`}
          className="rounded-xs font-mono text-code text-accent-blue outline-none hover:underline focus-visible:shadow-focus"
        >
          {s.name}
        </Link>
      ),
    },
    { key: "version", header: "Version", value: (s) => s.version, align: "right" },
    { key: "case_count", header: "Cases", value: (s) => s.case_count, align: "right" },
    { key: "created_at", header: "Created", value: (s) => s.created_at, render: (s) => date(s.created_at) },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (s) => (
        <Button data-testid={`run-suite-${s.name}`} variant="translucent" onClick={() => setRunning(s.id)}>
          Run
        </Button>
      ),
    },
  ];

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-12">
        <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Suites</h1>
        <Button
          data-testid="new-suite"
          onClick={() => {
            setDialogKey((k) => k + 1);
            setCreateOpen(true);
          }}
        >
          New suite
        </Button>
      </header>
      <Card className="mt-20">
        {suites === "loading" && <Skeleton className="h-120" />}
        {suites === "error" && <EmptyState title="Couldn't load suites" description="Check your connection and reload the page." />}
        {Array.isArray(suites) && (
          <DataTable
            caption="Suites"
            columns={columns}
            rows={suites}
            rowKey={(s) => s.id}
            empty={<EmptyState title="No suites yet" description="Create one from a YAML file to start running cases." />}
          />
        )}
      </Card>
      {createOpen && (
        <SuiteDialog
          key={dialogKey}
          projectId={projectId}
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            load();
          }}
        />
      )}
      {running && Array.isArray(suites) && (
        <RunSuiteDialog projectId={projectId} suites={suites} suiteId={running} onClose={() => setRunning(null)} />
      )}
    </>
  );
}

function SuiteDialog({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  // Keyed by the parent on each open, so a fresh mount clears the form — no reset effect.
  const [yaml, setYaml] = useState("");
  const [issues, setIssues] = useState<SuiteIssue[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setYaml(await file.text());
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!yaml.trim()) {
      setFormError("Paste or upload a suite YAML file.");
      return;
    }
    setFormError(null);
    setIssues([]);
    setBusy(true);
    const { data, error, response } = await api.POST("/projects/{project_id}/suites", {
      params: { path: { project_id: projectId } },
      body: { yaml },
    });
    setBusy(false);
    if (data) {
      onCreated();
      return;
    }
    if (response.status === 422) {
      const details = (error as { error?: { details?: SuiteIssue[] } })?.error?.details;
      if (details?.length) {
        setIssues(details);
        return;
      }
    }
    setFormError(apiErrorMessage(error));
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="New suite"
      actions={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="suite-form" disabled={busy}>
            {busy ? "Creating…" : "Create suite"}
          </Button>
        </>
      }
    >
      <form id="suite-form" className="flex flex-col gap-12 text-left" onSubmit={submit} noValidate>
        <div className="flex flex-col gap-6">
          <Label htmlFor="suite-yaml-file">Upload a YAML file</Label>
          <input
            id="suite-yaml-file"
            data-testid="suite-yaml-file"
            type="file"
            accept=".yaml,.yml"
            onChange={(e) => void onFile(e)}
            className="text-body-sm text-ink-muted"
          />
        </div>
        <div className="flex flex-col gap-6">
          <Label htmlFor="suite-yaml">…or paste it here</Label>
          <Textarea
            id="suite-yaml"
            data-testid="suite-yaml"
            className="min-h-240 font-mono text-code"
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            spellCheck={false}
          />
        </div>
        {issues.length > 0 && (
          <ul data-testid="suite-yaml-issues" className="flex flex-col gap-4 rounded-lg bg-surface-2 p-12 text-body-sm text-fail">
            {issues.map((issue, i) => (
              <li key={i}>
                {issue.line != null ? `Line ${issue.line}: ` : issue.path ? `${issue.path}: ` : ""}
                {issue.message}
              </li>
            ))}
          </ul>
        )}
        <FieldError id="suite-form-error">{formError}</FieldError>
      </form>
    </Dialog>
  );
}
