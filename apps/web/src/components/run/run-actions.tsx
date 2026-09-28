"use client";

import { type FormEvent, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/code";
import { Dialog } from "@/components/ui/dialog";
import { FieldError, Input, Label, Select } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api/client";
import { apiErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { date } from "@/lib/format";

type Run = components["schemas"]["RunDetailOut"];

type Props = {
  run: Run;
  projectId: string;
  /** Refetch the run (and its verdict) after an action changed it. */
  onChanged: () => void;
};

export function RunActions({ run, projectId, onChanged }: Props) {
  const toast = useToast();
  const [dialog, setDialog] = useState<"cancel" | "baseline" | "share" | null>(null);
  const live = run.status === "queued" || run.status === "running";

  async function download(format: "json" | "html") {
    // Through the API client (not a plain link), so an expired session refreshes first.
    const { data } = await api.GET("/runs/{run_id}/export", {
      params: { path: { run_id: run.id }, query: { format } },
      parseAs: "blob",
    });
    if (!data) {
      toast({ title: "Export failed", tone: "fail" });
      return;
    }
    const url = URL.createObjectURL(data);
    const link = Object.assign(document.createElement("a"), { href: url, download: `run-${run.id.slice(0, 8)}.${format}` });
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-wrap gap-8">
      {live && (
        <Button variant="secondary" onClick={() => setDialog("cancel")}>
          Cancel run
        </Button>
      )}
      <Button
        variant="secondary"
        disabled={run.status !== "completed"}
        title={run.status === "completed" ? undefined : "Only a completed run can be a baseline"}
        onClick={() => setDialog("baseline")}
      >
        Set as baseline
      </Button>
      <Button variant="secondary" onClick={() => download("json")}>
        Export JSON
      </Button>
      <Button variant="secondary" onClick={() => download("html")}>
        Export HTML
      </Button>
      <Button onClick={() => setDialog("share")}>Share</Button>

      <CancelDialog run={run} open={dialog === "cancel"} onClose={() => setDialog(null)} onDone={onChanged} />
      <BaselineDialog run={run} projectId={projectId} open={dialog === "baseline"} onClose={() => setDialog(null)} onDone={onChanged} />
      <ShareDialog run={run} open={dialog === "share"} onClose={() => setDialog(null)} onDone={onChanged} />
    </div>
  );
}

type DialogProps = { run: Run; open: boolean; onClose: () => void; onDone: () => void };

function CancelDialog({ run, open, onClose, onDone }: DialogProps) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function cancel() {
    setBusy(true);
    const { error } = await api.POST("/runs/{run_id}/cancel", { params: { path: { run_id: run.id } } });
    setBusy(false);
    onClose();
    toast(error ? { title: apiErrorMessage(error), tone: "fail" } : { title: "Run cancelled", tone: "pass" });
    onDone();
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Cancel this run?"
      actions={
        <>
          <Button variant="translucent" onClick={onClose}>
            Keep running
          </Button>
          <Button onClick={cancel} disabled={busy}>
            {busy ? "Cancelling…" : "Cancel run"}
          </Button>
        </>
      }
    >
      Attempts already finished are kept and summarized; the rest never run.
    </Dialog>
  );
}

function BaselineDialog({ run, projectId, open, onClose, onDone }: DialogProps & { projectId: string }) {
  const toast = useToast();
  const [branch, setBranch] = useState(run.branch ?? "main");
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!branch.trim()) {
      setError("Branch is required");
      return;
    }
    const { error: apiError } = await api.POST("/projects/{project_id}/baseline", {
      params: { path: { project_id: projectId } },
      body: { branch: branch.trim(), run_id: run.id },
    });
    if (apiError) {
      setError(apiErrorMessage(apiError));
      return;
    }
    setError(null);
    onClose();
    toast({ title: `Baseline for ${branch.trim()} set`, tone: "pass" });
    onDone();
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Set as baseline"
      actions={
        <>
          <Button variant="translucent" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form={`${id}-form`}>
            Set baseline
          </Button>
        </>
      }
    >
      <form id={`${id}-form`} onSubmit={submit} noValidate className="flex flex-col gap-6 text-left">
        <p className="mb-8">
          Later runs of <span className="text-ink">{run.suite_name}</span> against{" "}
          <span className="text-ink">{run.agent}</span> on this branch are compared with this one.
        </p>
        <Label htmlFor={`${id}-branch`}>Branch</Label>
        <Input
          id={`${id}-branch`}
          value={branch}
          onChange={(e) => setBranch(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
        />
        <FieldError id={`${id}-error`}>{error}</FieldError>
      </form>
    </Dialog>
  );
}

function ShareDialog({ run, open, onClose, onDone }: DialogProps) {
  const toast = useToast();
  const [days, setDays] = useState("30");
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const id = useId();

  async function create() {
    setBusy(true);
    const { data, error } = await api.POST("/runs/{run_id}/share", {
      params: { path: { run_id: run.id } },
      body: { expires_in_days: days ? Number(days) : null },
    });
    setBusy(false);
    if (!data) {
      toast({ title: apiErrorMessage(error), tone: "fail" });
      return;
    }
    // The API only knows the web origin when PUBLIC_WEB_URL is set.
    setLink(data.url ?? `${window.location.origin}/shared/${data.token}`);
    onDone();
  }

  async function revoke() {
    setBusy(true);
    const { response } = await api.DELETE("/runs/{run_id}/share", { params: { path: { run_id: run.id } } });
    setBusy(false);
    if (!response.ok) {
      toast({ title: "Couldn't revoke the link", tone: "fail" });
      return;
    }
    setLink(null);
    toast({ title: "Share link revoked", tone: "pass" });
    onDone();
  }

  function close() {
    setLink(null); // the token is shown once, like an API key
    onClose();
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Share a read-only link"
      actions={
        <>
          {(run.shared || link) && (
            <Button variant="translucent" onClick={revoke} disabled={busy}>
              Revoke link
            </Button>
          )}
          {!link && (
            <Button onClick={create} disabled={busy}>
              {run.shared ? "Replace link" : "Create link"}
            </Button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-12 text-left">
        <p>Anyone with the link sees the results and judge reasons, but not the agent&rsquo;s config or full traces.</p>
        {link ? (
          <div className="flex flex-col gap-6">
            <Label htmlFor={`${id}-link`}>Copy it now; it won&rsquo;t be shown again</Label>
            <div className="flex items-center gap-8">
              <Input id={`${id}-link`} readOnly value={link} className="font-mono text-code" onFocus={(e) => e.target.select()} />
              <CopyButton text={link} />
            </div>
          </div>
        ) : (
          <>
            {run.shared && (
              <p className="text-ink">
                A link is active{run.share_expires_at ? ` until ${date(run.share_expires_at)}` : " with no expiry"}. Replacing
                it stops the old one working.
              </p>
            )}
            <div className="flex flex-col gap-6">
              <Label htmlFor={`${id}-days`}>Expires</Label>
              <Select id={`${id}-days`} value={days} onChange={(e) => setDays(e.target.value)}>
                <option value="7">In 7 days</option>
                <option value="30">In 30 days</option>
                <option value="365">In a year</option>
                <option value="">Never</option>
              </Select>
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
