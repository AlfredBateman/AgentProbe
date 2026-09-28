"use client";

import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CodeBlock } from "@/components/ui/code";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, Input, Label } from "@/components/ui/field";
import { Badge } from "@/components/ui/status";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { requiredError } from "@/lib/validators";

type ApiKey = components["schemas"]["ApiKeyOut"];

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const formatDate = (iso: string | null) => (iso ? dateFormat.format(new Date(iso)) : "Never");

export default function SettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <>
      <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Settings</h1>
      <div className="mt-20 flex flex-col gap-20">
        <ApiKeysCard projectId={projectId} />
        <ModelConfigCard />
      </div>
    </>
  );
}

function ApiKeysCard({ projectId }: { projectId: string }) {
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
          <Button variant="translucent" onClick={() => revoke(k)}>
            Revoke
          </Button>
        ),
    },
  ];

  return (
    <Card title="API keys" actions={<Button onClick={() => setCreateOpen(true)}>Create key</Button>}>
      {justCreated && (
        <div className="mb-15 rounded-lg bg-surface-2 p-15">
          <p className="text-body-sm text-ink">
            <strong>{justCreated.label}</strong> — copy this key now. You won&rsquo;t be able to see it again.
          </p>
          <CodeBlock code={justCreated.key} className="mt-8" />
          <Button variant="secondary" className="mt-12" onClick={() => setJustCreated(null)}>
            Done
          </Button>
        </div>
      )}
      {keys === "loading" && <Skeleton className="h-120" />}
      {keys === "error" && <EmptyState title="Couldn't load API keys" description="Check your connection and reload the page." />}
      {Array.isArray(keys) && (
        <DataTable
          columns={columns}
          rows={keys}
          rowKey={(k) => k.id}
          caption="API keys"
          empty={<EmptyState title="No API keys yet" description="Create one for the CLI or CI to push runs with." />}
        />
      )}
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
    </Card>
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
      <form id="create-api-key" className="flex flex-col gap-15 text-left" onSubmit={onSubmit} noValidate>
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
        <FieldError id="create-key-error">{errors.form}</FieldError>
      </form>
    </Dialog>
  );
}

type LlmConfig = components["schemas"]["LlmConfigOut"];

function ModelConfigCard() {
  const [config, setConfig] = useState<LlmConfig | "loading" | "error">("loading");

  useEffect(() => {
    api.GET("/config/llm").then(({ data }) => setConfig(data ?? "error"));
  }, []);

  return (
    <Card title="Models">
      {config === "loading" && <Skeleton className="h-80" />}
      {config === "error" && <EmptyState title="Couldn't load model config" />}
      {typeof config === "object" && (
        <>
          <p className="text-body-sm text-ink-muted">
            Provider: <span className="text-ink">{config.provider}</span>. Set by the server operator — never
            configurable per project.
          </p>
          <dl className="mt-15 grid grid-cols-[auto_1fr] gap-x-20 gap-y-8 text-data">
            {Object.entries(config.models).map(([role, model]) => (
              <Fragment key={role}>
                <dt className="text-ink-muted capitalize">{role}</dt>
                <dd className="font-mono text-ink">{model}</dd>
              </Fragment>
            ))}
          </dl>
        </>
      )}
    </Card>
  );
}
