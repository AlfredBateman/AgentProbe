"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { RunSuiteDialog } from "@/components/run/run-suite-dialog";
import { CaseBrowser, type Version, VersionHistory } from "@/components/suite/suite-panels";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, Label, Textarea } from "@/components/ui/field";
import { StatusDot } from "@/components/ui/status";
import { Tabs, tabId } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { date } from "@/lib/format";

type Suite = components["schemas"]["SuiteDetailOut"];
type Issue = components["schemas"]["SuiteIssue"];
type Panel = "editor" | "cases" | "versions";
type Validation = { valid: true; cases: number } | { valid: false; issues: Issue[] } | "checking" | null;

const VALIDATE_AFTER_MS = 400;

/** One suite (SPEC.md §9.5, E3): its YAML editor (validated as you type; saving makes a new
 * version), its cases, and its version history. */
export default function SuitePage() {
  const { projectId, suiteId } = useParams<{ projectId: string; suiteId: string }>();
  const [suite, setSuite] = useState<Suite | "loading" | "error">("loading");
  const [versions, setVersions] = useState<Version[]>([]);
  const [panel, setPanel] = useState<Panel>("editor");
  const [running, setRunning] = useState(false);

  const load = useCallback(() => {
    const path = { suite_id: suiteId };
    Promise.all([api.GET("/suites/{suite_id}", { params: { path } }), api.GET("/suites/{suite_id}/versions", { params: { path } })]).then(
      ([s, v]) => {
        setSuite(s.data ?? "error");
        setVersions(v.data ?? []);
      },
    );
  }, [suiteId]);

  useEffect(() => {
    load();
  }, [load]);

  if (suite === "loading") return <Skeleton className="h-320" />;
  if (suite === "error") return <EmptyState title="Suite not found" description="It may have been deleted, or it belongs to another project." />;

  return (
    <>
      <header className="flex flex-col gap-15 tablet:flex-row tablet:items-start tablet:justify-between">
        <div className="min-w-0">
          <p className="text-data-label text-ink-muted">
            <Link href={`/projects/${projectId}/suites`} className="rounded-xs outline-none hover:text-ink focus-visible:shadow-focus">
              Suites
            </Link>{" "}
            / <span className="font-mono">{suite.name}</span>
          </p>
          <h1 className="mt-4 font-display text-dash-title-sm break-words tablet:text-dash-title">{suite.name}</h1>
          <p className="mt-8 text-data text-ink-muted">
            Version {suite.version} · {suite.case_count} {suite.case_count === 1 ? "case" : "cases"} · created {date(suite.created_at)}
          </p>
        </div>
        <Button data-testid="run-this-suite" onClick={() => setRunning(true)} className="self-start">
          Run
        </Button>
      </header>

      <Tabs
        aria-label="Suite"
        className="mt-20"
        value={panel}
        onValueChange={setPanel}
        items={[
          { value: "editor", label: "Editor" },
          { value: "cases", label: "Cases" },
          { value: "versions", label: `Versions (${versions.length})` },
        ]}
      />
      <Card className="mt-12" role="tabpanel" aria-labelledby={tabId(panel)}>
        {panel === "editor" && <SuiteEditor key={suite.version} suite={suite} onSaved={load} />}
        {panel === "cases" && <CaseBrowser key={suite.version} suiteId={suite.id} versions={versions} current={suite.version} />}
        {panel === "versions" && <VersionHistory suiteId={suite.id} versions={versions} current={suite.version} />}
      </Card>
      {running && (
        <RunSuiteDialog
          projectId={projectId}
          suites={[{ id: suite.id, name: suite.name, version: suite.version, case_count: suite.case_count, created_at: suite.created_at }]}
          suiteId={suite.id}
          onClose={() => setRunning(false)}
        />
      )}
    </>
  );
}

/** Keyed on the suite's version by the parent, so a save remounts it on the new text. */
function SuiteEditor({ suite, onSaved }: { suite: Suite; onSaved: () => void }) {
  const toast = useToast();
  const [yaml, setYaml] = useState(suite.yaml);
  const [checked, setValidation] = useState<Validation>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const dirty = yaml !== suite.yaml;
  // The saved text was valid when saved; only an edit needs (re)checking.
  const validation: Validation = dirty ? checked : { valid: true, cases: suite.case_count };

  useEffect(() => {
    if (!dirty) return;
    let live = true; // a slower, older response must not overwrite a newer one
    const timer = setTimeout(async () => {
      setValidation("checking");
      const { data } = await api.POST("/suites/validate", { body: { yaml } });
      if (!live || !data) return;
      setValidation(data.valid ? { valid: true, cases: data.case_count ?? 0 } : { valid: false, issues: data.issues ?? [] });
    }, VALIDATE_AFTER_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [yaml, dirty]);

  function jumpTo(line: number) {
    const area = ref.current;
    if (!area) return;
    const lines = yaml.split("\n");
    const start = lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
    area.focus();
    area.setSelectionRange(start, start + (lines[line - 1]?.length ?? 0));
    area.scrollTop = (line - 1) * (parseFloat(getComputedStyle(area).lineHeight) || 20) - area.clientHeight / 3;
  }

  async function save() {
    setBusy(true);
    setError(null);
    const { data, error: apiError, response } = await api.PUT("/suites/{suite_id}", { params: { path: { suite_id: suite.id } }, body: { yaml } });
    setBusy(false);
    if (data) {
      toast({ title: data.version === suite.version ? "No changes to save" : `Saved as version ${data.version}`, tone: "pass" });
      onSaved();
      return;
    }
    const details = (apiError as { error?: { details?: Issue[] } })?.error?.details;
    if (response.status === 422 && details?.length) setValidation({ valid: false, issues: details });
    else setError(apiErrorMessage(apiError));
  }

  const invalid = typeof validation === "object" && validation !== null && !validation.valid;
  return (
    <div className="flex flex-col gap-12">
      <div className="flex flex-wrap items-center justify-between gap-12">
        <Label htmlFor="suite-editor">YAML</Label>
        <p aria-live="polite" data-testid="suite-validation" className="flex items-center gap-6 text-data-label">
          {validation === "checking" && <span className="text-ink-muted">Checking…</span>}
          {typeof validation === "object" && validation?.valid && (
            <>
              <StatusDot status="pass" decorative />
              <span className="text-pass">
                Valid · {validation.cases} {validation.cases === 1 ? "case" : "cases"}
              </span>
            </>
          )}
          {invalid && (
            <>
              <StatusDot status="fail" decorative />
              <span className="text-fail">
                {validation.issues.length} {validation.issues.length === 1 ? "problem" : "problems"}
              </span>
            </>
          )}
        </p>
      </div>
      <Textarea
        id="suite-editor"
        ref={ref}
        data-testid="suite-editor"
        className="min-h-400 font-mono text-code"
        spellCheck={false}
        value={yaml}
        onChange={(e) => setYaml(e.target.value)}
        aria-invalid={invalid}
        aria-describedby={invalid ? "suite-issues" : undefined}
      />
      {invalid && (
        <ul id="suite-issues" data-testid="suite-issues" className="flex flex-col gap-4 rounded-lg bg-surface-2 p-12 text-body-sm text-fail">
          {validation.issues.map((issue, i) => (
            <li key={i}>
              {issue.line != null ? (
                <button
                  type="button"
                  onClick={() => jumpTo(issue.line!)}
                  className="cursor-pointer rounded-xs text-left underline-offset-2 outline-none hover:underline focus-visible:shadow-focus"
                >
                  Line {issue.line}: {issue.message}
                </button>
              ) : (
                <>
                  {issue.path ? `${issue.path}: ` : ""}
                  {issue.message}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <FieldError id="suite-save-error">{error}</FieldError>
      <div className="flex flex-wrap items-center justify-end gap-8">
        {dirty && <span className="mr-auto text-data-label text-ink-muted">Unsaved changes. Saving makes version {suite.version + 1}; runs keep the version they used.</span>}
        <Button variant="secondary" onClick={() => setYaml(suite.yaml)} disabled={!dirty || busy}>
          Discard
        </Button>
        <Button data-testid="save-suite" onClick={() => void save()} disabled={!dirty || busy || invalid || validation === "checking"}>
          {busy ? "Saving…" : "Save"}
        </Button>
      </div>
    </div>
  );
}
