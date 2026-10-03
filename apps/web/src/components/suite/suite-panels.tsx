"use client";

import { type ReactNode, useEffect, useState } from "react";
import { CodeBlock, jsonText, PlainText } from "@/components/ui/code";
import { type Column, DataTable } from "@/components/ui/data-table";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { Label, Select } from "@/components/ui/field";
import { Badge } from "@/components/ui/status";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { date } from "@/lib/format";
import { type DiffLine, lineDiff } from "@/lib/line-diff";

type Case = components["schemas"]["CaseOut"];
export type Version = components["schemas"]["SuiteVersionOut"];

const preview = (c: Case) =>
  c.input ?? (c.call ? `call ${String((c.call as { tool?: unknown }).tool ?? "?")}(…)` : "—");

/** One version's cases (E3): what each sends and which judges check it. */
export function CaseBrowser({ suiteId, versions, current }: { suiteId: string; versions: Version[]; current: number }) {
  const [version, setVersion] = useState(current);
  const [cases, setCases] = useState<Case[] | "loading" | "error">("loading");

  useEffect(() => {
    let live = true;
    api
      .GET("/suites/{suite_id}/cases", { params: { path: { suite_id: suiteId }, query: { version } } })
      .then(({ data }) => live && setCases(data ?? "error"));
    return () => {
      live = false;
    };
  }, [suiteId, version]);

  const columns: Column<Case>[] = [
    { key: "id", header: "Case", value: (c) => c.id, render: (c) => <span className="font-mono text-code">{c.id}</span> },
    { key: "attack", header: "Attack", value: (c) => c.attack ?? "", render: (c) => (c.attack ? <span className="font-mono text-code">{c.attack}</span> : "—") },
    {
      key: "input",
      header: "Input",
      value: (c) => preview(c),
      render: (c) => (
        <span className="block max-w-320 truncate text-ink-muted" title={preview(c)}>
          {preview(c)}
        </span>
      ),
    },
    { key: "judges", header: "Judges", value: (c) => c.judges.length, render: (c) => c.judges.map((j) => String(j.judge)).join(", ") },
    { key: "context", header: "Documents", align: "right", value: (c) => c.context_count, render: (c) => c.context_count || "—" },
  ];

  return (
    <div className="flex flex-col gap-15">
      {versions.length > 1 && (
        <div className="flex flex-wrap items-center gap-12">
          <Label htmlFor="cases-version">Version</Label>
          <Select
            id="cases-version"
            data-testid="cases-version"
            value={version}
            onChange={(e) => {
              setCases("loading");
              setVersion(Number(e.target.value));
            }}
          >
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                v{v.version}
                {v.version === current ? " (current)" : ""}
              </option>
            ))}
          </Select>
        </div>
      )}
      {cases === "loading" && <Skeleton className="h-120" />}
      {cases === "error" && <EmptyState title="Couldn't load the cases" description="Reload the page to try again." />}
      {Array.isArray(cases) && (
        <DataTable
          caption={`Cases in version ${version}`}
          columns={columns}
          rows={cases}
          rowKey={(c) => c.id}
          expandLabel={(c) => `case ${c.id}`}
          expand={(c) => (
            <div className="flex flex-col gap-12">
              {c.input != null && <Detail label="Input"><PlainText text={c.input} /></Detail>}
              {c.call && <Detail label="Tool call"><PlainText text={jsonText(c.call)} /></Detail>}
              <Detail label="Judges">
                <PlainText text={jsonText(c.judges)} />
              </Detail>
            </div>
          )}
        />
      )}
    </div>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <span className="text-data-label text-ink-muted">{label}</span>
      {children}
    </div>
  );
}

/** Every version, newest first; expanding one shows what changed from the version before it. */
export function VersionHistory({ suiteId, versions, current }: { suiteId: string; versions: Version[]; current: number }) {
  const columns: Column<Version>[] = [
    {
      key: "version",
      header: "Version",
      value: (v) => v.version,
      render: (v) => (
        <span className="inline-flex items-center gap-8">
          v{v.version}
          {v.version === current && <Badge status="stable">Current</Badge>}
        </span>
      ),
    },
    { key: "saved", header: "Saved", value: (v) => v.created_at ?? "", render: (v) => (v.created_at ? date(v.created_at) : v.has_yaml ? "Not recorded" : "Before history was kept") },
    { key: "cases", header: "Cases", align: "right", value: (v) => v.case_count },
    { key: "runs", header: "Runs", align: "right", value: (v) => v.run_count },
  ];
  return (
    <DataTable
      caption="Suite versions"
      columns={columns}
      rows={versions}
      rowKey={(v) => String(v.version)}
      expandLabel={(v) => `version ${v.version}`}
      expand={(v) => <VersionDetail suiteId={suiteId} version={v} previous={versions.find((p) => p.version === v.version - 1)} />}
    />
  );
}

function VersionDetail({ suiteId, version, previous }: { suiteId: string; version: Version; previous?: Version }) {
  const [yaml, setYaml] = useState<{ now: string | null; before: string | null } | null>(null);

  useEffect(() => {
    const get = (v: number) =>
      api.GET("/suites/{suite_id}/versions/{version}", { params: { path: { suite_id: suiteId, version: v } } }).then(({ data }) => data?.yaml ?? null);
    Promise.all([get(version.version), previous?.has_yaml ? get(previous.version) : Promise.resolve(null)]).then(([now, before]) =>
      setYaml({ now, before }),
    );
  }, [suiteId, version.version, previous]);

  if (!yaml) return <Skeleton className="h-80" />;
  if (yaml.now === null)
    return (
      <p className="text-body-sm text-ink-muted">
        Saved before AgentProbe kept each version&apos;s YAML. Its {version.case_count} cases are in the Cases tab.
      </p>
    );
  return (
    <div className="flex flex-col gap-12">
      {previous && yaml.before !== null ? (
        <section aria-label={`Changes from version ${previous.version}`}>
          <h3 className="mb-6 text-data-label text-ink-muted">Changes from v{previous.version}</h3>
          <YamlDiff before={yaml.before} after={yaml.now} />
        </section>
      ) : (
        <p className="text-body-sm text-ink-muted">{previous ? `v${previous.version} has no saved YAML to compare with.` : "The first version."}</p>
      )}
      <details>
        <summary className="cursor-pointer text-data-label text-ink-muted">Full YAML of v{version.version}</summary>
        <CodeBlock code={yaml.now} label={`v${version.version}`} className="mt-8" />
      </details>
    </div>
  );
}

const CONTEXT = 3; // unchanged lines kept around each change

/** A folded line diff as plain text: +/− marks (and screen-reader words), never color alone. */
function YamlDiff({ before, after }: { before: string; after: string }) {
  const diff = lineDiff(before, after);
  if (diff === null) return <p className="text-body-sm text-ink-muted">Too large to compare here.</p>;
  if (diff.every((l) => l.kind === "same")) return <p className="text-body-sm text-ink-muted">No changes.</p>;
  const near = new Set<number>();
  diff.forEach((l, i) => {
    if (l.kind !== "same") for (let k = i - CONTEXT; k <= i + CONTEXT; k++) near.add(k);
  });
  const rows: (DiffLine | number)[] = []; // a number stands for that many folded unchanged lines
  diff.forEach((l, i) => {
    if (near.has(i)) rows.push(l);
    else if (typeof rows.at(-1) === "number") rows[rows.length - 1] = (rows.at(-1) as number) + 1;
    else rows.push(1);
  });
  return (
    <pre data-testid="yaml-diff" className="overflow-x-auto rounded-lg bg-canvas py-8 font-mono text-code">
      {rows.map((row, i) =>
        typeof row === "number" ? (
          <div key={i} className="px-12 text-ink-muted">
            ··· {row} unchanged {row === 1 ? "line" : "lines"}
          </div>
        ) : (
          <div key={i} className={row.kind === "add" ? "bg-surface-2 px-12 text-ink" : row.kind === "del" ? "px-12 text-ink-muted line-through" : "px-12 text-ink-muted"}>
            <span aria-hidden className="inline-block w-16 select-none">
              {row.kind === "add" ? "+" : row.kind === "del" ? "−" : " "}
            </span>
            {row.kind !== "same" && <span className="sr-only">{row.kind === "add" ? "Added: " : "Removed: "}</span>}
            {row.text || " "}
          </div>
        ),
      )}
    </pre>
  );
}
