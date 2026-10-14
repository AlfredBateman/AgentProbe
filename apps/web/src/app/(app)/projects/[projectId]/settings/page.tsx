"use client";

import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/code";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, FormError, Input, Label } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/status";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { useReveal, useStagger } from "@/lib/motion/hooks";
import { requiredError } from "@/lib/validators";

type ApiKey = components["schemas"]["ApiKeyOut"];

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatDate = (iso: string | null) => (iso ? dateFormat.format(new Date(iso)) : "Never");

export default function SettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const headerRef = useRef<HTMLElement>(null);
  useReveal(headerRef);
  return (
    <>
      <header ref={headerRef} className="border-b border-hairline-strong pb-16">
        <p className="type-micro text-ink-muted">
          [ Project ] <span aria-hidden>{"///"}</span> Keys, models, alerts
        </p>
        <h1 className="mt-8 type-display-md">Settings</h1>
      </header>
      {/* Keys take the wide column. The narrow one holds read-only panels, so a new section
          (alerts, when they exist) is one more panel in it. */}
      <div className="mt-24 grid items-start gap-16 desktop:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <ApiKeysPanel projectId={projectId} />
        <div className="flex flex-col gap-16">
          <ModelConfigPanel />
          <AlertsPanel />
        </div>
      </div>
    </>
  );
}

function ApiKeysPanel({ projectId }: { projectId: string }) {
  const toast = useToast();
  const [keys, setKeys] = useState<ApiKey[] | "loading" | "error">("loading");
  const [createOpen, setCreateOpen] = useState(false);
  const [justCreated, setJustCreated] = useState<{ label: string; key: string } | null>(null);

  const load = useCallback(() => {
    api.GET("/projects/{project_id}/api-keys", { params: { path: { project_id: projectId } } }).then(({ data }) =>
      setKeys(data ?? "error"),
    );
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function revoke(key: ApiKey) {
    const { response } = await api.DELETE("/projects/{project_id}/api-keys/{key_id}", {
      params: { path: { project_id: projectId, key_id: key.id } },
    });
    if (response.ok) {
      toast({ title: `Revoked "${key.label}"`, tone: "pass" });
      load();
    } else {
      toast({ title: "Couldn't revoke the key", tone: "fail" });
    }
  }

  const columns: Column<ApiKey>[] = [
    { key: "label", header: "Label", value: (k) => k.label },
    { key: "last4", header: "Key", render: (k) => <span className="font-mono">ap_…{k.last4}</span> },
    { key: "created_at", header: "Created", value: (k) => k.created_at, render: (k) => formatDate(k.created_at) },
    { key: "last_used_at", header: "Last used", value: (k) => k.last_used_at, render: (k) => formatDate(k.last_used_at) },
    {
      key: "status",
      header: "Status",
      render: (k) => (k.revoked_at ? <Badge status="error">Revoked</Badge> : <Badge status="pass">Active</Badge>),
    },
    {
      key: "actions",
      header: "",
      render: (k) =>
        k.revoked_at ? null : (
          <Button variant="danger" onClick={() => revoke(k)}>
            Revoke
          </Button>
        ),
    },
  ];

  return (
    <Panel title="API keys" actions={<Button onClick={() => setCreateOpen(true)}>Create key</Button>}>
      {/* Reveal once: the key exists in this state only. Leaving, reloading or pressing Done
          drops it, and the API never returns it again (only its last four characters). */}
      {justCreated && (
        <div className="mb-16 border-2 border-accent p-16">
          <p className="type-label text-accent">[ Shown once ]</p>
          <p className="mt-8 type-body text-ink">
            <strong>{justCreated.label}</strong> — copy this key now. You won&rsquo;t be able to see it again.
          </p>
          <CodeBlock code={justCreated.key} label="API key" className="mt-12" />
          <Button variant="secondary" className="mt-12" onClick={() => setJustCreated(null)}>
            Done
          </Button>
        </div>
      )}
      {keys === "loading" && <Skeleton className="h-120" />}
      {keys === "error" && <EmptyState title="Couldn't load API keys" description="Check your connection and reload the page." />}
      {Array.isArray(keys) && <KeysTable columns={columns} keys={keys} />}
      <CreateKeyDialog
        projectId={projectId}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(created) => {
          setCreateOpen(false);
          setJustCreated({ label: created.label, key: created.key });
          load();
        }}
      />
    </Panel>
  );
}

function KeysTable({ columns, keys }: { columns: Column<ApiKey>[]; keys: ApiKey[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useStagger(ref, "tbody tr");
  return (
    <div ref={ref} className="border border-hairline">
      <DataTable
        columns={columns}
        rows={keys}
        rowKey={(k) => k.id}
        caption="API keys"
        empty={<EmptyState title="No API keys yet" description="Create one for the CLI or CI to push runs with." />}
      />
    </div>
  );
}

function CreateKeyDialog({
  projectId,
  open,
  onClose,
  onCreated,
}: {
  projectId: string;
  open: boolean;
  onClose: () => void;
  onCreated: (created: { label: string; key: string }) => void;
}) {
  const [label, setLabel] = useState("");
  const [errors, setErrors] = useState<{ label?: string; form?: string }>({});
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const labelError = requiredError(label, "Label");
    if (labelError) {
      setErrors({ label: labelError });
      return;
    }
    setErrors({});
    setSubmitting(true);
    const { data, error, response } = await api.POST("/projects/{project_id}/api-keys", {
      params: { path: { project_id: projectId } },
      body: { label },
    });
    setSubmitting(false);
    if (data) {
      setLabel("");
      onCreated(data);
      return;
    }
    if (response.status === 422) {
      setErrors(apiFieldErrors(error));
      return;
    }
    setErrors({ form: apiErrorMessage(error) });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Create API key"
      actions={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-api-key" disabled={submitting}>
            {submitting ? "Creating…" : "Create key"}
          </Button>
        </>
      }
    >
      <form id="create-api-key" className="flex flex-col gap-16 text-left" onSubmit={onSubmit} noValidate>
        <div className="flex flex-col gap-6">
          <Label htmlFor="key-label">Label</Label>
          <Input
            id="key-label"
            placeholder="ci"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            aria-invalid={!!errors.label}
            aria-describedby={errors.label ? "key-label-error" : undefined}
          />
          <FieldError id="key-label-error">{errors.label}</FieldError>
        </div>
        <FormError id="create-key-error">{errors.form}</FormError>
      </form>
    </Dialog>
  );
}

type LlmConfig = components["schemas"]["LlmConfigOut"];

function ModelConfigPanel() {
  const [config, setConfig] = useState<LlmConfig | "loading" | "error">("loading");

  useEffect(() => {
    api.GET("/config/llm").then(({ data }) => setConfig(data ?? "error"));
  }, []);

  return (
    <Panel title="Models">
      {config === "loading" && <Skeleton className="h-80" />}
      {config === "error" && <EmptyState title="Couldn't load model config" />}
      {typeof config === "object" && (
        <>
          <p className="type-body-sm text-ink-muted">
            Provider: <span className="text-ink">{config.provider}</span>. Set by the server operator — never
            configurable per project.
          </p>
          <dl className="mt-16 grid grid-cols-[auto_minmax(0,1fr)] gap-x-24 gap-y-8">
            {Object.entries(config.models).map(([role, model]) => (
              <Fragment key={role}>
                <dt className="type-label text-ink-muted">{role}</dt>
                <dd className="type-code break-words text-ink">{model}</dd>
              </Fragment>
            ))}
          </dl>
        </>
      )}
    </Panel>
  );
}

/** Where alerts will live. There is no setting to show yet, so it says so and names what does
 * report a regression today. */
function AlertsPanel() {
  return (
    <Panel title="Alerts" actions={<span className="type-micro text-ink-muted">Not available yet</span>}>
      <p className="type-body-sm text-ink-muted">
        A regression fails the CLI run and the GitHub Action check. Alerts inside the app, and where they go, will be set here.
      </p>
    </Panel>
  );
}
