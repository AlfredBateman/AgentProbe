"use client";

import { useParams } from "next/navigation";
import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, Input, Label, Select, Textarea } from "@/components/ui/field";
import { Badge, StatusDot } from "@/components/ui/status";
import { useToast } from "@/components/ui/toast";
import { type AdapterType, configFrom, type Draft, draftFrom, type FieldErrors } from "@/lib/agent-form";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type Agent = components["schemas"]["AgentOut"];
// configFrom builds a plain JSON object; the API validates its shape (the generated union is stricter).
type AgentConfig = components["schemas"]["AgentIn"]["config"];
type AgentDialogState = { mode: "create" } | { mode: "edit"; agent: Agent };
type TestResult = { success: boolean; message: string };
// "keep": leave the stored header as it is; "set": send a new one; "clear": remove it.
type AuthMode = "keep" | "set" | "clear";

const urlOf = (agent: Agent) => String((agent.config as { url?: unknown }).url ?? "");
const ADAPTERS: Record<AdapterType, string> = { http: "HTTP", mcp: "MCP (HTTP transport)" };

/** Agents (SPEC.md §9.4, E3): add and edit HTTP and MCP agents with their full config and an
 * optional write-only auth header, test a draft or a saved agent, delete with a warning. */
export default function AgentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const toast = useToast();
  const [agents, setAgents] = useState<Agent[] | "loading" | "error">("loading");
  const [dialog, setDialog] = useState<AgentDialogState | null>(null);
  const [deleting, setDeleting] = useState<Agent | null>(null);
  const [testing, setTesting] = useState<string | null>(null);

  const load = useCallback(() => {
    api.GET("/projects/{project_id}/agents", { params: { path: { project_id: projectId } } }).then(({ data }) =>
      setAgents(data ?? "error"),
    );
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function testSaved(agent: Agent) {
    setTesting(agent.id);
    const { data, error } = await api.POST("/agents/{agent_id}/test", { params: { path: { agent_id: agent.id } } });
    setTesting(null);
    const result = data ?? { success: false, message: apiErrorMessage(error) };
    toast({ title: `${agent.name}: ${result.message}`, tone: result.success ? "pass" : "fail" });
  }

  const columns: Column<Agent>[] = [
    // Adapter under the name and a capped URL, so the table fits its card at 810px (ADR 0028 §8).
    {
      key: "name",
      header: "Name",
      value: (a) => a.name,
      render: (a) => (
        <span className="flex flex-col items-start gap-4">
          <span className="font-mono text-code">{a.name}</span>
          <Badge status="stable">{a.adapter_type}</Badge>
        </span>
      ),
    },
    {
      key: "url",
      header: "URL",
      value: (a) => urlOf(a),
      render: (a) => (
        <span className="block max-w-200 truncate text-ink-muted desktop:max-w-420" title={urlOf(a)}>
          {urlOf(a)}
        </span>
      ),
    },
    { key: "secret", header: "Auth", value: (a) => (a.has_secret ? 1 : 0), render: (a) => (a.has_secret ? "Set" : "—") },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (a) => (
        <div className="flex justify-end gap-8">
          <Button variant="translucent" data-testid={`test-agent-${a.name}`} onClick={() => void testSaved(a)} disabled={testing === a.id}>
            {testing === a.id ? "Testing…" : "Test"}
          </Button>
          <Button variant="translucent" onClick={() => setDialog({ mode: "edit", agent: a })}>
            Edit
          </Button>
          <Button variant="translucent" onClick={() => setDeleting(a)}>
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
            empty={<EmptyState title="No agents yet" description="Add one to point a suite at your agent's HTTP or MCP endpoint." />}
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
      {deleting && (
        <DeleteAgentDialog
          key={deleting.id}
          projectId={projectId}
          agent={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            toast({ title: `Deleted "${deleting.name}"`, tone: "pass" });
            setDeleting(null);
            load();
          }}
        />
      )}
    </>
  );
}

const RUNS_COUNTED = 200;

/** Deleting an agent deletes its runs too (runs.agent_id is ON DELETE CASCADE), so say so first. */
function DeleteAgentDialog({ projectId, agent, onClose, onDeleted }: { projectId: string; agent: Agent; onClose: () => void; onDeleted: () => void }) {
  const [runs, setRuns] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .GET("/projects/{project_id}/runs", { params: { path: { project_id: projectId }, query: { limit: RUNS_COUNTED } } })
      .then(({ data }) => setRuns(data ? data.filter((r) => r.agent_id === agent.id).length : null));
  }, [projectId, agent.id]);

  async function remove() {
    setBusy(true);
    const { response, error: apiError } = await api.DELETE("/agents/{agent_id}", { params: { path: { agent_id: agent.id } } });
    setBusy(false);
    if (response.ok) onDeleted();
    else setError(apiErrorMessage(apiError));
  }

  const runText = runs === null ? "all of its runs" : runs >= RUNS_COUNTED ? `its ${RUNS_COUNTED}+ runs` : runs === 1 ? "its 1 run" : `its ${runs} runs`;
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Delete ${agent.name}?`}
      actions={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button data-testid="confirm-delete-agent" onClick={() => void remove()} disabled={busy}>
            {busy ? "Deleting…" : "Delete agent"}
          </Button>
        </>
      }
    >
      <p>
        This also deletes {runText}, with their results, traces and any baselines set from them, and the agent&apos;s stored auth
        header. It can&apos;t be undone. Suites that name <span className="font-mono text-code text-ink">{agent.name}</span> can&apos;t run
        until you add an agent with that name again.
      </p>
      <FieldError id="delete-agent-error">{error}</FieldError>
    </Dialog>
  );
}

function AgentDialog({ projectId, dialog, onClose, onSaved }: { projectId: string; dialog: AgentDialogState; onClose: () => void; onSaved: () => void }) {
  // Keyed by the parent on dialog identity (create vs. which agent), so a fresh mount is the reset.
  const stored = dialog.mode === "edit" ? dialog.agent : undefined;
  const [draft, setDraftState] = useState<Draft>(() => draftFrom(stored));
  const [dirty, setDirty] = useState(false);
  const [auth, setAuth] = useState<{ mode: AuthMode; name: string; value: string }>({
    mode: stored?.has_secret ? "keep" : "set",
    name: "Authorization",
    value: "",
  });
  const [errors, setErrors] = useState<FieldErrors & { form?: string; auth?: string }>({});
  const [test, setTest] = useState<TestResult | "testing" | null>(null);
  const [busy, setBusy] = useState(false);

  const setDraft = (patch: Partial<Draft>) => {
    setDraftState((d) => ({ ...d, ...patch }));
    setDirty(true);
  };
  const authHeader = auth.mode === "set" && auth.value ? { name: auth.name.trim(), value: auth.value } : undefined;

  function build() {
    const { config, errors: fieldErrors } = configFrom(draft, stored);
    const authError = auth.mode === "set" && auth.value && !auth.name.trim() ? "Name the header, e.g. Authorization." : undefined;
    setErrors({ ...fieldErrors, auth: authError });
    return authError ? undefined : config;
  }

  async function testConnection() {
    // An unedited saved agent is tested as saved, so its stored auth header is sent too.
    if (stored && !dirty && auth.mode === "keep") {
      setTest("testing");
      const { data, error } = await api.POST("/agents/{agent_id}/test", { params: { path: { agent_id: stored.id } } });
      setTest(data ?? { success: false, message: apiErrorMessage(error) });
      return;
    }
    const config = build();
    if (!config) return;
    setTest("testing");
    const { data, error } = await api.POST("/projects/{project_id}/agents/test", {
      params: { path: { project_id: projectId } },
      body: { config: config as AgentConfig, ...(authHeader ? { auth_header: authHeader } : {}) },
    });
    setTest(data ?? { success: false, message: apiErrorMessage(error) });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const config = build();
    if (!config) return;
    setBusy(true);
    const body = { name: draft.name.trim(), config: config as AgentConfig, ...(authHeader ? { auth_header: authHeader } : {}) };
    const { data, error, response } = stored
      ? await api.PUT("/agents/{agent_id}", {
          params: { path: { agent_id: stored.id } },
          body: { ...body, clear_secret: auth.mode === "clear" },
        })
      : await api.POST("/projects/{project_id}/agents", { params: { path: { project_id: projectId } }, body });
    setBusy(false);
    if (data) return onSaved();
    setErrors(response.status === 422 ? { ...apiFieldErrors(error), form: apiErrorMessage(error) } : { form: apiErrorMessage(error) });
  }

  const http = draft.adapterType === "http";
  const untestedSecret = stored?.has_secret && auth.mode === "keep" && dirty;
  return (
    <Dialog
      open
      onClose={onClose}
      title={stored ? "Edit agent" : "New agent"}
      actions={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" variant="translucent" data-testid="test-connection" onClick={() => void testConnection()} disabled={test === "testing" || !draft.url}>
            {test === "testing" ? "Testing…" : "Test connection"}
          </Button>
          <Button type="submit" form="agent-form" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <form id="agent-form" className="flex max-h-[60dvh] flex-col gap-15 overflow-y-auto pr-4 text-left" onSubmit={submit} noValidate>
        <Field id="agent-name" label="Name" error={errors.name}>
          <Input id="agent-name" data-testid="agent-name" value={draft.name} onChange={(e) => setDraft({ name: e.target.value })} aria-invalid={!!errors.name} aria-describedby={errors.name ? "agent-name-error" : undefined} />
        </Field>
        <Field id="agent-adapter" label="Adapter">
          <Select id="agent-adapter" data-testid="agent-adapter" value={draft.adapterType} onChange={(e) => setDraft({ adapterType: e.target.value as AdapterType })}>
            {Object.entries(ADAPTERS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          {!http && (
            <p className="text-data-label text-ink-muted">
              MCP agents can be saved and tested here. Server runs use HTTP agents for now; run MCP suites with the CLI.
            </p>
          )}
        </Field>
        <Field id="agent-url" label={http ? "URL" : "MCP endpoint URL"} error={errors.url}>
          <Input
            id="agent-url"
            data-testid="agent-url"
            placeholder={http ? "http://127.0.0.1:9000/support/v1/chat" : "http://127.0.0.1:9000/mcp-tools/mcp"}
            value={draft.url}
            onChange={(e) => setDraft({ url: e.target.value })}
            aria-invalid={!!errors.url}
            aria-describedby={errors.url ? "agent-url-error" : undefined}
          />
        </Field>
        <label className="flex items-center gap-8 text-body-sm text-ink">
          <input type="checkbox" checked={draft.allowPrivate} onChange={(e) => setDraft({ allowPrivate: e.target.checked })} />
          Allow private targets (localhost, RFC 1918) — needed for the bundled demo agents
        </label>

        <fieldset className="flex flex-col gap-8 rounded-lg border border-hairline p-12">
          <legend className="px-4 text-data-label text-ink-muted">Auth header (stored encrypted, never shown again)</legend>
          {stored?.has_secret && auth.mode !== "set" ? (
            <div className="flex flex-wrap items-center justify-between gap-8">
              <p data-testid="auth-state" className="text-body-sm text-ink">
                {auth.mode === "keep" ? "An auth header is stored." : "The stored auth header will be removed on save."}
              </p>
              <div className="flex gap-8">
                {auth.mode === "keep" ? (
                  <>
                    <Button variant="translucent" onClick={() => setAuth({ ...auth, mode: "set" })}>
                      Replace
                    </Button>
                    <Button variant="translucent" data-testid="remove-auth" onClick={() => setAuth({ ...auth, mode: "clear" })}>
                      Remove
                    </Button>
                  </>
                ) : (
                  <Button variant="translucent" onClick={() => setAuth({ ...auth, mode: "keep" })}>
                    Keep it
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-8 tablet:grid-cols-[1fr_2fr]">
              <div className="flex flex-col gap-6">
                <Label htmlFor="auth-name">Header</Label>
                <Input id="auth-name" value={auth.name} onChange={(e) => setAuth({ ...auth, name: e.target.value })} aria-invalid={!!errors.auth} />
              </div>
              <div className="flex flex-col gap-6">
                <Label htmlFor="auth-value">Value {stored?.has_secret ? "(replaces the stored one)" : "(optional)"}</Label>
                <Input id="auth-value" data-testid="auth-value" type="password" autoComplete="off" value={auth.value} onChange={(e) => setAuth({ ...auth, value: e.target.value })} />
              </div>
              {stored?.has_secret && (
                <Button variant="translucent" className="justify-self-start" onClick={() => setAuth({ ...auth, mode: "keep", value: "" })}>
                  Keep the stored one
                </Button>
              )}
              <FieldError id="auth-error">{errors.auth}</FieldError>
            </div>
          )}
        </fieldset>

        <details>
          <summary className="cursor-pointer text-data-label text-ink-muted">Request and limits</summary>
          <div className="mt-10 flex flex-col gap-10">
            {http && (
              <>
                <Field id="agent-method" label="Method">
                  <Select id="agent-method" value={draft.method} onChange={(e) => setDraft({ method: e.target.value as Draft["method"] })}>
                    {["POST", "PUT", "PATCH"].map((m) => (
                      <option key={m}>{m}</option>
                    ))}
                  </Select>
                </Field>
                <Field id="agent-template" label="Request body template (JSON; {{input}} and {{documents}} are filled in)" error={errors.template}>
                  <Textarea id="agent-template" data-testid="agent-template" className="min-h-120 font-mono text-code" spellCheck={false} value={draft.template} onChange={(e) => setDraft({ template: e.target.value })} aria-invalid={!!errors.template} aria-describedby={errors.template ? "agent-template-error" : undefined} />
                </Field>
              </>
            )}
            <Field id="agent-headers" label="Plain headers (one Name: value per line; put secrets in the auth header)" error={errors.headers}>
              <Textarea id="agent-headers" data-testid="agent-headers" className="min-h-72 font-mono text-code" spellCheck={false} value={draft.headers} onChange={(e) => setDraft({ headers: e.target.value })} aria-invalid={!!errors.headers} aria-describedby={errors.headers ? "agent-headers-error" : undefined} />
            </Field>
            <div className="grid grid-cols-2 gap-10">
              <Field id="agent-timeout" label="Timeout (ms)" error={errors.timeoutMs}>
                <Input id="agent-timeout" inputMode="numeric" value={draft.timeoutMs} onChange={(e) => setDraft({ timeoutMs: e.target.value })} aria-invalid={!!errors.timeoutMs} aria-describedby={errors.timeoutMs ? "agent-timeout-error" : undefined} />
              </Field>
              <Field id="agent-retries" label="Retries" error={errors.maxRetries}>
                <Input id="agent-retries" inputMode="numeric" value={draft.maxRetries} onChange={(e) => setDraft({ maxRetries: e.target.value })} aria-invalid={!!errors.maxRetries} aria-describedby={errors.maxRetries ? "agent-retries-error" : undefined} />
              </Field>
            </div>
            {http && (
              <label className="flex items-center gap-8 text-body-sm text-ink">
                <input type="checkbox" checked={draft.followRedirects} onChange={(e) => setDraft({ followRedirects: e.target.checked })} />
                Follow redirects (at most 5, each re-checked)
              </label>
            )}
          </div>
        </details>

        {http && (
          <details>
            <summary className="cursor-pointer text-data-label text-ink-muted">Response mapping (JSONPath)</summary>
            <div className="mt-10 grid grid-cols-1 gap-10 tablet:grid-cols-2">
              {(
                [
                  ["output", "Output"],
                  ["toolCalls", "Tool calls (optional)"],
                  ["toolName", "Tool name, within a call"],
                  ["toolArguments", "Tool arguments, within a call"],
                  ["inputTokens", "Input tokens (optional)"],
                  ["outputTokens", "Output tokens (optional)"],
                  ["totalTokens", "Total tokens (optional)"],
                ] as const
              ).map(([key, label]) => (
                <Field key={key} id={`agent-${key}`} label={label}>
                  <Input id={`agent-${key}`} className="font-mono text-code" value={draft[key]} onChange={(e) => setDraft({ [key]: e.target.value })} />
                </Field>
              ))}
            </div>
          </details>
        )}

        {test && test !== "testing" && (
          <p data-testid="test-connection-result" className="flex items-start gap-8 text-body-sm">
            <StatusDot status={test.success ? "pass" : "fail"} decorative className="mt-4" />
            <span className={test.success ? "text-pass" : "text-fail"}>{test.message}</span>
          </p>
        )}
        {untestedSecret && <p className="text-data-label text-ink-muted">Edited settings are tested without the stored auth header. Save first to test with it.</p>}
        <FieldError id="agent-form-error">{errors.form}</FieldError>
      </form>
    </Dialog>
  );
}

function Field({ id, label, error, children }: { id: string; label: string; error?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <Label htmlFor={id}>{label}</Label>
      {children}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </div>
  );
}
