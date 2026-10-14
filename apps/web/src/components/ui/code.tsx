"use client";

import { type ReactNode, useEffect, useState } from "react";
import { cx } from "@/lib/cx";
import { Button } from "./button";
import { CheckIcon, CopyIcon } from "./icons";

type CopyState = "idle" | "copied" | "failed";
const RESET_MS = 2000;

export function CopyButton({ text, className }: { text: string; className?: string }) {
  const [state, setState] = useState<CopyState>("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), RESET_MS);
    return () => clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text); // absent or rejected outside a secure context
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  const label = { idle: "Copy", copied: "Copied", failed: "Copy failed" }[state];
  return (
    <>
      <Button variant="icon" aria-label={label} title={label} onClick={copy} className={className}>
        {state === "copied" ? <CheckIcon /> : <CopyIcon />}
      </Button>
      <span aria-live="polite" className="sr-only">
        {state === "idle" ? "" : label}
      </span>
    </>
  );
}

/**
 * What a piece of text is, in HTML terms: `samp` is output (an agent's reply, a tool result),
 * `kbd` is input typed at something (an attack payload, the case input), `code` is source (YAML).
 */
export type TextKind = "samp" | "kbd" | "code";

const PLAIN_TEXT_LIMIT = 2000;

/**
 * Untrusted text (agent output, attack payloads, tool arguments and results) as a text child
 * only: never HTML, never markdown. Values past `limit` characters are cut, with a toggle.
 */
export function PlainText({
  text,
  limit = PLAIN_TEXT_LIMIT,
  mono = true,
  as: Tag = "samp",
  className,
}: {
  text: string;
  limit?: number;
  /** Body type instead of code type, for prose such as judge reasons. */
  mono?: boolean;
  as?: TextKind;
  className?: string;
}) {
  const [full, setFull] = useState(false);
  const long = text.length > limit;
  return (
    <div className={cx("min-w-0", className)}>
      {/* The type classes go on the inner element: samp, kbd and code carry their own monospace default. */}
      <pre className="break-words whitespace-pre-wrap">
        <Tag className={cx(mono ? "type-code" : "type-body-sm", "text-ink")}>{long && !full ? `${text.slice(0, limit)}…` : text}</Tag>
      </pre>
      {long && (
        <button
          type="button"
          aria-expanded={full}
          onClick={() => setFull(!full)}
          className="mt-4 cursor-pointer type-label text-accent hover:underline"
        >
          {full ? "Show less" : `Show full (${text.length.toLocaleString()} characters)`}
        </button>
      )}
    </div>
  );
}

/** A JSON value (tool arguments and results) as indented plain text; strings stay as they are. */
export const jsonText = (value: unknown) => (typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "null");

/**
 * Traces, YAML and payloads. The text is rendered as a text child only: agent output and attack
 * payloads are untrusted and must never become HTML.
 *
 * `body` replaces the read-only text with something that edits it (the suite editor), inside the
 * same frame; `code` is still what the copy button holds. `footer` sits under the body, divided
 * by a line (validation messages). `invalid` turns the frame's edge red.
 */
export function CodeBlock({
  code,
  label,
  as: Tag = "code",
  className,
  body,
  footer,
  invalid,
}: {
  code: string;
  label?: ReactNode;
  as?: TextKind;
  className?: string;
  body?: ReactNode;
  footer?: ReactNode;
  invalid?: boolean;
}) {
  return (
    <figure className={cx("min-w-0 overflow-hidden border bg-canvas", invalid ? "border-fail" : "border-hairline-strong", className)}>
      <figcaption className="flex items-center justify-between gap-8 border-b border-hairline bg-surface-1 py-4 pr-4 pl-16 type-micro text-ink-muted">
        {label ?? ""}
        <CopyButton text={code} />
      </figcaption>
      {/* Long lines wrap (an install line is two git URLs) instead of running off the panel;
          a single unbreakable token still scrolls. Focusable, so a keyboard user can scroll it.
          Only the display wraps: the copy button holds the whole, unbroken text. */}
      {body ?? (
        <pre tabIndex={0} className="overflow-x-auto p-16 break-words whitespace-pre-wrap">
          <Tag className="type-code text-ink">{code}</Tag>
        </pre>
      )}
      {footer && <div className="border-t border-hairline">{footer}</div>}
    </figure>
  );
}
