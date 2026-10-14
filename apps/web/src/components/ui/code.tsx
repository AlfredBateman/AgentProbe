"use client";

import { type ReactNode, useEffect, useState } from "react";
import { cx } from "@/lib/cx";
import { Button } from "./button";
import { CheckIcon, CopyIcon } from "./icons";

type CopyState = "idle" | "copied" | "failed";
const RESET_MS = 2000;

/** `name` says what is copied ("step 3"), for a page with several copy buttons. */
export function CopyButton({ text, name, className }: { text: string; name?: string; className?: string }) {
  const [state, setState] = useState<CopyState>("idle");

  useEffect(() => {
    if (state === "idle") return;
    const timer = setTimeout(() => setState("idle"), RESET_MS);
    return () => clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(visibleText(text)); // absent or rejected outside a secure context
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  const label = { idle: name ? `Copy ${name}` : "Copy", copied: "Copied", failed: "Copy failed" }[state];
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

// C0/C1 controls (ANSI escapes start with ESC or CSI) except tab and newline, and the bidi
// controls that can reorder what a reader sees (Trojan Source).
const CONTROL = /[\u0000-\u0008\u000B-\u001F\u007F-\u009F]/g;
const BIDI = /[؜‎‏‪-‮⁦-⁩]/g;
const hex = (c: string) => c.charCodeAt(0).toString(16).toUpperCase().padStart(4, "0");

/**
 * Untrusted text as it is shown and copied: every control and bidi character becomes a visible,
 * inert stand-in (ESC is "␛", U+202E is "⟨U+202E⟩"), so an ANSI sequence can't restyle a
 * terminal it's pasted into and an override can't reorder what's on screen. Lossy by design.
 */
export const visibleText = (text: string) =>
  text
    .replace(CONTROL, (c) => (c === "\u007F" ? "␡" : c < " " ? String.fromCharCode(0x2400 + c.charCodeAt(0)) : `⟨U+${hex(c)}⟩`))
    .replace(BIDI, (c) => `⟨U+${hex(c)}⟩`);

/** JSON with the characters JSON.stringify leaves raw (C1, bidi) escaped as \uXXXX: same value, inert text. */
export const safeJson = (value: unknown) =>
  (JSON.stringify(value, null, 2) ?? "null").replace(/[\u0080-\u009F؜‎‏‪-‮⁦-⁩]/g, (c) => `\\u${hex(c)}`);

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
        <Tag className={cx(mono ? "type-code" : "type-body-sm", "text-ink")}>{visibleText(long && !full ? `${text.slice(0, limit)}…` : text)}</Tag>
      </pre>
      {long && (
        <button
          type="button"
          aria-expanded={full}
          onClick={() => setFull(!full)}
          className="tap mt-4 cursor-pointer type-label text-accent hover:underline"
        >
          {full ? "Show less" : `Show full (${text.length.toLocaleString()} characters)`}
        </button>
      )}
    </div>
  );
}

/** A JSON value (tool arguments and results) as indented plain text; strings stay as they are. */
export const jsonText = (value: unknown) => (typeof value === "string" ? value : safeJson(value));

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
          <Tag className="type-code text-ink">{visibleText(code)}</Tag>
        </pre>
      )}
      {footer && <div className="border-t border-hairline">{footer}</div>}
    </figure>
  );
}
