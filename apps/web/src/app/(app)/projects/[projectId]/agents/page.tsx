"use client";

import { useParams } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, Input, Label } from "@/components/ui/field";
import { Badge, StatusDot } from "@/components/ui/status";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { requiredError } from "@/lib/validators";

type Agent = components["schemas"]["AgentOut"];
type AgentDialogState = { mode: "create" } | { mode: "edit"; agent: Agent };
type AgentConfigShape = {
  url?: string;
  allow_private?: boolean;
  response?: { output?: string; tool_calls?: string | null; total_tokens?: string | null };
};

const urlOf = (agent: Agent) => (agent.config as AgentConfigShape).url ?? "";

/** Agents CRUD (a minimal E3 slice: just enough to add an HTTP agent, test its connection,
 * and repoint it later — no MCP/auth-header UI yet). */
export default function AgentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const toast = useToast();
  const [agents, setAgents] = useState<Agent[] | "loading" | "error">("loading");
  const [dialog, setDialog] = useState<AgentDialogState | null>(null);

  const load = useCallback(() => {
    api.GET("/projects/{project_id}/agents", { params: { path: { project_id: projectId } } }).then(({ data }) =>
      setAgents(data ?? "error"),
    );
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(agent: Agent) {
    const { response } = await api.DELETE("/agents/{agent_id}", { params: { path: { agent_id: agent.id } } });
    if (response.ok) {
      toast({ title: `Deleted "${agent.name}"`, tone: "pass" });
      load();
    } else {
      toast({ title: "Couldn't delete the agent", tone: "fail" });
    }
  }

  const columns: Column<Agent>[] = [
    { key: "name", header: "Name", value: (a) => a.name, render: (a) => <span className="font-mono text-code">{a.name}</span> },
    {
      key: "adapter_type",
      header: "Adapter",
      value: (a) => a.adapter_type,
      render: (a) => <Badge status="stable">{a.adapter_type}</Badge>,
    },
    { key: "url", header: "URL", value: (a) => urlOf(a), render: (a) => <span className="break-all text-ink-muted">{urlOf(a)}</span> },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (a) => (
        <div className="flex justify-end gap-8">
          <Button variant="translucent" onClick={() => setDialog({ mode: "edit", agent: a })}>
            Edit
          </Button>
          <Button variant="translucent" onClick={() => remove(a)}>
            Delete
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-12">
        <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Agents</h1>
        <Button data-testid="new-agent" onClick={() => setDialog({ mode: "create" })}>
          New agent
        </Button>
      </header>
      <Card className="mt-20">
        {agents === "loading" && <Skeleton className="h-120" />}
        {agents === "error" && <EmptyState title="Couldn't load agents" description="Check your connection and reload the page." />}
        {Array.isArray(agents) && (
          <DataTable
            caption="Agents"
            columns={columns}
            rows={agents}
            rowKey={(a) => a.id}
            empty={<EmptyState title="No agents yet" description="Add one to point a suite at your agent's HTTP endpoint." />}
          />
        )}
      </Card>
      {dialog && (
        <AgentDialog
          key={dialog.mode === "edit" ? dialog.agent.id : "create"}
          projectId={projectId}
          dialog={dialog}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            load();
          }}
        />
      )}
    </>
  );
}

type Draft = {
  name: string;
  url: string;
  allowPrivate: boolean;
  outputPath: string;
  toolCallsPath: string;
  totalTokensPath: string;
};

function draftFrom(dialog: AgentDialogState | null): Draft {
  if (dialog?.mode === "edit") {
    const config = dialog.agent.config as AgentConfigShape;
    return {
      name: dialog.agent.name,
      url: config.url ?? "",
      allowPrivate: config.allow_private ?? false,
      outputPath: config.response?.output ?? "$.output",
      toolCallsPath: config.response?.tool_calls ?? "$.tool_calls",
      totalTokensPath: config.response?.total_tokens ?? "$.usage.total_tokens",
    };
  }
  // Defaults match the bundled demo agents' response shape, so pointing at one just works.
  return {
    name: "",
    url: "",
    allowPrivate: true,
    outputPath: "$.output",
    toolCallsPath: "$.tool_calls",
    totalTokensPath: "$.usage.total_tokens",
  };
}

function configFrom(draft: Draft) {
  return {
    adapter_type: "http" as const,
    url: draft.url,
    method: "POST" as const,
    timeout_ms: 30_000,
    max_retries: 2,
    follow_redirects: false,
    allow_private: draft.allowPrivate,
    response: {
      output: draft.outputPath || "$.output",
      tool_calls: draft.toolCallsPath || null,
      tool_name: "$.tool",
      tool_arguments: "$.arguments",
      total_tokens: draft.totalTokensPath || null,
    },
  };
}

function AgentDialog({
  projectId,
  dialog,
  onClose,
  onSaved,
}: {
  projectId: string;
  dialog: AgentDialogState;
  onClose: () => void;
  onSaved: () => void;
}) {
  // Keyed by the parent on dialog identity (create vs. which agent), so a fresh mount is all
  // the reset a mode switch needs — no effect syncing state to a changed prop.
  const [draft, setDraft] = useState<Draft>(() => draftFrom(dialog));
  const [errors, setErrors] = useState<{ name?: string; url?: string; form?: string }>({});
  const [test, setTest] = useState<{ success: boolean; message: string } | "testing" | null>(null);
  const [busy, setBusy] = useState(false);

  async function testConnection() {
    setTest("testing");
    const { data, error } = await api.POST("/projects/{project_id}/agents/test", {
      params: { path: { project_id: projectId } },
      body: { config: configFrom(draft) },
    });
    setTest(data ?? { success: false, message: apiErrorMessage(error) });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const nameError = requiredError(draft.name, "Name");
    const urlError = requiredError(draft.url, "URL");
    if (nameError || urlError) {
      setErrors({ name: nameError ?? undefined, url: urlError ?? undefined });
      return;
    }
    setErrors({});
    setBusy(true);
    const config = configFrom(draft);
    const { data, error, response } =
      dialog?.mode === "edit"
        ? await api.PUT("/agents/{agent_id}", {
            params: { path: { agent_id: dialog.agent.id } },
            body: { name: draft.name, config, clear_secret: false },
          })
        : await api.POST("/projects/{project_id}/agents", {
            params: { path: { project_id: projectId } },
            body: { name: draft.name, config },
          });
    setBusy(false);
    if (data) {
      onSaved();
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
      open
      onClose={onClose}
      title={dialog.mode === "edit" ? "Edit agent" : "New agent"}
      actions={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="translucent"
            data-testid="test-connection"
            onClick={() => void testConnection()}
            disabled={test === "testing" || !draft.url}
          >
            {test === "testing" ? "Testing…" : "Test connection"}
          </Button>
          <Button type="submit" form="agent-form" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <form id="agent-form" className="flex flex-col gap-15 text-left" onSubmit={submit} noValidate>
        <div className="flex flex-col gap-6">
          <Label htmlFor="agent-name">Name</Label>
          <Input
            id="agent-name"
            data-testid="agent-name"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? "agent-name-error" : undefined}
          />
          <FieldError id="agent-name-error">{errors.name}</FieldError>
        </div>
        <div className="flex flex-col gap-6">
          <Label htmlFor="agent-url">URL</Label>
          <Input
            id="agent-url"
            data-testid="agent-url"
            placeholder="http://127.0.0.1:9000/support/v1/chat"
            value={draft.url}
            onChange={(e) => setDraft({ ...draft, url: e.target.value })}
            aria-invalid={!!errors.url}
            aria-describedby={errors.url ? "agent-url-error" : undefined}
          />
          <FieldError id="agent-url-error">{errors.url}</FieldError>
        </div>
        <label className="flex items-center gap-8 text-body-sm text-ink">
          <input
            type="checkbox"
            checked={draft.allowPrivate}
            onChange={(e) => setDraft({ ...draft, allowPrivate: e.target.checked })}
          />
          Allow private targets (localhost, RFC 1918) — needed for the bundled demo agents
        </label>
        <details>
          <summary className="cursor-pointer text-data-label text-ink-muted">Response mapping</summary>
          <div className="mt-8 flex flex-col gap-10">
            <div className="flex flex-col gap-6">
              <Label htmlFor="agent-output-path">Output (JSONPath)</Label>
              <Input
                id="agent-output-path"
                value={draft.outputPath}
                onChange={(e) => setDraft({ ...draft, outputPath: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-6">
              <Label htmlFor="agent-tool-calls-path">Tool calls (JSONPath, optional)</Label>
              <Input
                id="agent-tool-calls-path"
                value={draft.toolCallsPath}
                onChange={(e) => setDraft({ ...draft, toolCallsPath: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-6">
              <Label htmlFor="agent-tokens-path">Total tokens (JSONPath, optional)</Label>
              <Input
                id="agent-tokens-path"
                value={draft.totalTokensPath}
                onChange={(e) => setDraft({ ...draft, totalTokensPath: e.target.value })}
              />
            </div>
          </div>
        </details>
        {test && test !== "testing" && (
          <p data-testid="test-connection-result" className="flex items-start gap-8 text-body-sm">
            <StatusDot status={test.success ? "pass" : "fail"} decorative className="mt-4" />
            <span className={test.success ? "text-pass" : "text-fail"}>{test.message}</span>
          </p>
        )}
        <FieldError id="agent-form-error">{errors.form}</FieldError>
      </form>
    </Dialog>
  );
}
