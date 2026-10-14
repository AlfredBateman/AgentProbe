"use client";

import { useRef } from "react";
import { CodeBlock } from "@/components/ui/code";
import type { components } from "@/lib/api/schema";

export type Issue = components["schemas"]["SuiteIssue"];

const issueLines = (issues: Issue[]) => new Set(issues.flatMap((i) => (i.line != null ? [i.line] : [])));

/**
 * The suite YAML as an editable CodeBlock: a line-number gutter that marks the lines a
 * validation issue points at, and the issues themselves under the text, inside the same frame.
 * The text is a textarea's value, never HTML. Long lines scroll rather than wrap, so the gutter
 * and the text stay one line to one number.
 */
export function YamlEditor({ value, onChange, issues = [], invalid = false }: { value: string; onChange: (yaml: string) => void; issues?: Issue[]; invalid?: boolean }) {
  const area = useRef<HTMLTextAreaElement>(null);
  const gutter = useRef<HTMLDivElement>(null);
  const bad = issueLines(issues);
  const lines = value.split("\n").length;

  function jumpTo(line: number) {
    const el = area.current;
    if (!el) return;
    const rows = value.split("\n");
    const start = rows.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
    el.focus();
    el.setSelectionRange(start, start + (rows[line - 1]?.length ?? 0));
    el.scrollTop = (line - 1) * (parseFloat(getComputedStyle(el).lineHeight) || 20) - el.clientHeight / 3;
  }

  const body = (
    <div className="flex">
      {/* The gutter has no in-flow content, so the textarea sets the height; the numbers are
          absolutely placed inside it and scrolled in step with the text. */}
      <div aria-hidden className="relative w-48 shrink-0 border-r border-hairline bg-surface-1 select-none">
        <div ref={gutter} className="absolute inset-0 overflow-hidden py-16 text-right type-code text-ink-muted">
          {Array.from({ length: lines }, (_, i) => (
            <div key={i} className={bad.has(i + 1) ? "relative pr-8 text-fail" : "pr-8"}>
              {bad.has(i + 1) && <span className="absolute top-1/2 left-4 size-10 -translate-y-1/2 mark-fail" />}
              {i + 1}
            </div>
          ))}
        </div>
      </div>
      <textarea
        ref={area}
        id="suite-editor"
        data-testid="suite-editor"
        aria-label="YAML"
        aria-invalid={invalid}
        aria-describedby={invalid ? "suite-issues" : undefined}
        className="block min-h-400 min-w-0 flex-1 resize-y bg-canvas p-16 type-code text-ink"
        spellCheck={false}
        wrap="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => {
          if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop;
        }}
      />
    </div>
  );

  const footer = invalid && (
    <ul id="suite-issues" data-testid="suite-issues" className="flex flex-col gap-4 p-12 type-body-sm text-fail">
      {issues.map((issue, i) => (
        <li key={i}>
          {issue.line != null ? (
            <button type="button" onClick={() => jumpTo(issue.line!)} className="cursor-pointer text-left underline-offset-2 hover:underline">
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
  );

  return <CodeBlock code={value} label="suite.yaml" body={body} footer={footer} invalid={invalid} />;
}
