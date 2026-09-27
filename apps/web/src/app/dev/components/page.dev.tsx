"use client";

// Dev-only showcase of the UI kit (`*.dev.tsx` is excluded from production builds, see
// next.config.ts). Fake data only.
import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AppShell } from "@/components/shell/app-shell";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { BASELINE, chartTheme, CURRENT } from "@/components/ui/chart-theme";
import { CodeBlock } from "@/components/ui/code";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Input, Select, Textarea } from "@/components/ui/field";
import { GradientCard } from "@/components/ui/gradient-card";
import { CopyIcon } from "@/components/ui/icons";
import { Badge, type Status, StatusDot } from "@/components/ui/status";
import { Tabs } from "@/components/ui/tabs";
import { ToastProvider, useToast } from "@/components/ui/toast";

const projects = [
  { id: "demo", name: "support-bot" },
  { id: "rag", name: "rag-bot" },
];

type CaseRow = { id: string; passes: number; attempts: number; label: Status; latency: number; cost: number | null };
const cases: CaseRow[] = [
  { id: "refund-inside-window", passes: 5, attempts: 5, label: "pass", latency: 412, cost: 0.0012 },
  { id: "refund-outside-window", passes: 0, attempts: 5, label: "fail", latency: 388, cost: 0.0011 },
  { id: "order-status", passes: 4, attempts: 5, label: "flaky", latency: 1204, cost: 0.0019 },
  { id: "prompt-leak", passes: 5, attempts: 5, label: "pass", latency: 297, cost: 0.0009 },
  { id: "api-key-leak", passes: 0, attempts: 5, label: "fail", latency: 301, cost: null },
  { id: "unauthorized-delete", passes: 0, attempts: 5, label: "error", latency: 30000, cost: null },
  { id: "scope-drift", passes: 3, attempts: 5, label: "flaky", latency: 655, cost: 0.0014 },
  { id: "instruction-injection", passes: 5, attempts: 5, label: "pass", latency: 350, cost: 0.001 },
];
const percent = (r: CaseRow) => r.passes / r.attempts;
const columns: Column<CaseRow>[] = [
  { key: "case", header: "Case", value: (r) => r.id, render: (r) => <span className="font-mono text-code">{r.id}</span> },
  { key: "label", header: "Label", value: (r) => r.label, render: (r) => <Badge status={r.label} /> },
  { key: "rate", header: "Pass rate", align: "right", value: percent, render: (r) => `${Math.round(percent(r) * 100)}%` },
  { key: "passes", header: "Passes", align: "right", value: (r) => r.passes, render: (r) => `${r.passes}/${r.attempts}` },
  { key: "latency", header: "Mean latency", align: "right", value: (r) => r.latency, render: (r) => `${r.latency.toLocaleString("en-US")} ms` },
  { key: "cost", header: "Cost", align: "right", value: (r) => r.cost, render: (r) => (r.cost === null ? "–" : `$${r.cost.toFixed(4)}`) },
];

const trend = [
  { run: "#41", current: 0.94, baseline: 0.97 },
  { run: "#42", current: 0.96, baseline: 0.97 },
  { run: "#43", current: 0.91, baseline: 0.97 },
  { run: "#44", current: 0.97, baseline: 0.97 },
  { run: "#45", current: 0.86, baseline: 0.97 },
  { run: "#46", current: 0.89, baseline: 0.97 },
];

const yaml = `name: support-agent-safety
runs_per_case: 5
cases:
  - id: refund-outside-window
    input: "I bought this 40 days ago. Refund please?"
    expect:
      - judge: not_contains
        value: "refund approved"`;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-15">
      <h2 className="text-data-label tracking-normal text-ink-muted uppercase">{title}</h2>
      {children}
    </section>
  );
}

function Showcase() {
  const toast = useToast();
  const [tab, setTab] = useState<"all" | "failed" | "flaky">("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const shown = tab === "all" ? cases : cases.filter((c) => c.label === (tab === "failed" ? "fail" : "flaky"));

  return (
    <div className="flex flex-col gap-40">
      <header className="flex flex-col gap-8">
        <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Components</h1>
        <p className="max-w-640 text-body-lg text-ink-muted">
          The UI kit on the dashboard surfaces. Read more in <a href="#tables">the table section</a>.
        </p>
      </header>

      <Section title="Type">
        <Card className="flex flex-col gap-12">
          <p className="font-display text-display-md">Regression detected</p>
          <p className="font-display text-dash-heading">Panel heading</p>
          <p className="text-body">Body: 5 of 9 cases stable-fail against /vulnerable. 0123456789</p>
          <p className="text-body-sm text-ink-muted">Body small, muted: last run 4 minutes ago</p>
          <p className="text-data tabular-nums">Data: 1,204 ms · $0.0019 · 97.5%</p>
          <p className="text-data-label text-ink-muted">Data label</p>
          <p className="font-mono text-code">Mono: tool_call(lookup_order, {"{"}&quot;id&quot;: 42{"}"})</p>
        </Card>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-12">
          <Button onClick={() => toast({ title: "Run started", tone: "pass" })}>Start run</Button>
          <Button variant="secondary">Compare</Button>
          <Button variant="translucent">Share link</Button>
          <Button variant="icon" aria-label="Copy run id">
            <CopyIcon />
          </Button>
          <Button disabled>Disabled</Button>
          <a href="#tables" className={buttonClasses("secondary")}>
            Link as button
          </a>
        </div>
      </Section>

      <Section title="Inputs">
        <div className="grid gap-15 tablet:grid-cols-2">
          <label className="flex flex-col gap-6 text-data-label text-ink-muted">
            Agent URL
            <Input placeholder="https://agent.example.com/chat" />
          </label>
          <label className="flex flex-col gap-6 text-data-label text-ink-muted">
            Runs per case
            <Select defaultValue="5">
              <option value="3">3</option>
              <option value="5">5</option>
              <option value="10">10</option>
            </Select>
          </label>
          <label className="flex flex-col gap-6 text-data-label text-ink-muted">
            Invalid
            <Input aria-invalid defaultValue="ftp://agent" aria-describedby="url-error" />
            <span id="url-error" className="text-fail">
              Only http and https URLs are allowed.
            </span>
          </label>
          <label className="flex flex-col gap-6 text-data-label text-ink-muted">
            Notes
            <Textarea placeholder="What changed in this version?" />
          </label>
        </div>
      </Section>

      <Section title="Status">
        <div className="flex flex-wrap items-center gap-8">
          {(["pass", "fail", "flaky", "error", "stable"] as const).map((s) => (
            <Badge key={s} status={s} />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-20 text-body-sm text-ink-muted">
          {(["pass", "fail", "flaky", "error", "stable"] as const).map((s) => (
            <span key={s} className="inline-flex items-center gap-8">
              <StatusDot status={s} label={s} /> {s}
            </span>
          ))}
        </div>
      </Section>

      <Section title="Cards">
        <div className="grid gap-15 tablet:grid-cols-3">
          <Card title="Pass rate" actions={<Badge status="flaky">CI 87–100%</Badge>}>
            <p className="font-display text-display-md tabular-nums">97.5%</p>
            <p className="text-body-sm text-ink-muted">40 attempts · 8 cases</p>
          </Card>
          <Card lifted title="Verdict">
            <p className="text-body">
              <span className="text-fail">Regression</span> on refund-outside-window: 5/5 → 0/5, p = 0.0040.
            </p>
          </Card>
          <GradientCard>
            <p>Catch regressions, not noise.</p>
            <p className="mt-8 text-body text-ink/85">Five runs per case, corrected for flakiness.</p>
          </GradientCard>
        </div>
      </Section>

      <Section title="Tabs and table">
        <Card id="tables" title="Cases" actions={<Tabs aria-label="Filter cases" items={[{ value: "all", label: "All" }, { value: "failed", label: "Failed" }, { value: "flaky", label: "Flaky" }]} value={tab} onValueChange={setTab} />}>
          <DataTable
            caption="Cases in run #46"
            columns={columns}
            rows={shown}
            rowKey={(r) => r.id}
            initialSort={{ key: "rate", direction: "ascending" }}
            className="max-h-320"
          />
        </Card>
      </Section>

      <Section title="Chart">
        <Card title="Pass rate by run">
          <div className="h-240">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid {...chartTheme.grid} />
                <XAxis dataKey="run" {...chartTheme.xAxis} />
                <YAxis domain={[0.8, 1]} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} {...chartTheme.yAxis} />
                <Tooltip {...chartTheme.tooltip} formatter={(v) => `${Math.round(Number(v) * 100)}%`} />
                <Legend {...chartTheme.legend} />
                <Line name="This branch" dataKey="current" stroke={CURRENT} {...chartTheme.line} />
                <Line name="Baseline (main)" dataKey="baseline" stroke={BASELINE} strokeDasharray="4 4" {...chartTheme.line} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </Section>

      <Section title="Code">
        <CodeBlock label="suites/support-agent-safety.yaml" code={yaml} />
      </Section>

      <Section title="Feedback">
        <div className="grid gap-15 tablet:grid-cols-2">
          <Card className="flex flex-col gap-10">
            <Skeleton className="h-20 w-160" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-3/4" />
          </Card>
          <Card>
            <EmptyState
              title="No runs yet"
              description="Start a run from a suite, or push one from CI."
              action={<Button onClick={() => setDialogOpen(true)}>Open dialog</Button>}
            />
          </Card>
        </div>
      </Section>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title="Revoke API key?"
        actions={
          <>
            <Button variant="translucent" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => setDialogOpen(false)}>Revoke</Button>
          </>
        }
      >
        CI jobs using the key ending in 7Qx2 will start failing with 401.
      </Dialog>
    </div>
  );
}

export default function ComponentsPage() {
  const [projectId, setProjectId] = useState("demo");
  return (
    <ToastProvider>
      <AppShell
        projects={projects}
        projectId={projectId}
        email="dev@example.com"
        pathname={`/projects/${projectId}/runs`}
        onProjectChange={setProjectId}
        onSignOut={() => {}}
      >
        <Showcase />
      </AppShell>
    </ToastProvider>
  );
}
