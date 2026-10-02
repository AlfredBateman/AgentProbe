"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label, Select } from "@/components/ui/field";
import { api } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type Suite = components["schemas"]["SuiteOut"];

/** Start a run of a suite (E2's "Run a suite", E3's per-suite Run): which suite, how many
 * attempts per case, and whether judges use the server's live LLM. Mock is the default. */
export function RunSuiteDialog({
  projectId,
  suites,
  suiteId,
  onClose,
}: {
  projectId: string;
  suites: Suite[];
  /** Preselects a suite; the picker still lets the user change it. */
  suiteId?: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const [picked, setPicked] = useState(suiteId ?? suites[0]?.id ?? "");
  const [runs, setRuns] = useState("");
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const runsInvalid = runs !== "" && !(Number.isInteger(Number(runs)) && Number(runs) >= 1 && Number(runs) <= 20);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (runsInvalid || !picked) return;
    setBusy(true);
    setError(null);
    const { data, error: apiError } = await api.POST("/suites/{suite_id}/runs", {
      params: { path: { suite_id: picked } },
      body: { mock: !live, ...(runs ? { runs_per_case: Number(runs) } : {}) },
    });
    setBusy(false);
    if (data) router.push(`/projects/${projectId}/runs/${data.id}`);
    else setError(apiErrorMessage(apiError));
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title="Run a suite"
      actions={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          {suites.length > 0 && (
            <Button type="submit" form="run-form" data-testid="start-run" disabled={busy || runsInvalid}>
              {busy ? "Starting…" : "Start run"}
            </Button>
          )}
        </>
      }
    >
      {suites.length === 0 ? (
        <p>
          There are no suites in this project yet.{" "}
          <Link href={`/projects/${projectId}/suites`} className="rounded-xs text-accent-blue outline-none hover:underline focus-visible:shadow-focus">
            Create one
          </Link>{" "}
          first.
        </p>
      ) : (
        <form id="run-form" className="flex flex-col gap-15 text-left" onSubmit={submit} noValidate>
          <div className="flex flex-col gap-6">
            <Label htmlFor="run-suite">Suite</Label>
            <Select id="run-suite" data-testid="run-dialog-suite" value={picked} onChange={(e) => setPicked(e.target.value)}>
              {suites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} (v{s.version}, {s.case_count} {s.case_count === 1 ? "case" : "cases"})
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-6">
            <Label htmlFor="run-runs">Attempts per case</Label>
            <Input
              id="run-runs"
              data-testid="run-dialog-runs"
              inputMode="numeric"
              placeholder="The suite's runs_per_case"
              value={runs}
              onChange={(e) => setRuns(e.target.value.trim())}
              aria-invalid={runsInvalid}
              aria-describedby="run-runs-hint"
            />
            {runsInvalid ? (
              <FieldError id="run-runs-hint">A whole number from 1 to 20.</FieldError>
            ) : (
              <p id="run-runs-hint" className="text-data-label text-ink-muted">
                Leave empty for the suite&apos;s own setting. A regression needs 5 or more to be flagged.
              </p>
            )}
          </div>
          <label className="flex items-start gap-8 text-body-sm text-ink">
            <input type="checkbox" className="mt-4" checked={live} onChange={(e) => setLive(e.target.checked)} />
            Judge with the server&apos;s live LLM (spends quota; off uses the offline mock judge)
          </label>
          <FieldError id="run-form-error">{error}</FieldError>
        </form>
      )}
    </Dialog>
  );
}
