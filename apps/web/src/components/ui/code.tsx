"use client";

import { useEffect, useState } from "react";
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
      <Button variant="icon" aria-label={label} title={label} onClick={copy} className={cx("size-32 pointer-coarse:size-44", className)}>
        {state === "copied" ? <CheckIcon className="text-pass" /> : <CopyIcon />}
      </Button>
      <span aria-live="polite" className="sr-only">
        {state === "idle" ? "" : label}
      </span>
    </>
  );
}

/**
 * Traces, YAML and payloads. The text is rendered as a text child only: agent output and attack
 * payloads are untrusted and must never become HTML.
 */
export function CodeBlock({ code, label, className }: { code: string; label?: string; className?: string }) {
  return (
    <figure className={cx("min-w-0 overflow-hidden rounded-lg bg-surface-1", className)}>
      <figcaption className="flex min-h-40 items-center justify-between gap-8 border-b border-hairline-soft py-4 pr-4 pl-15 text-data-label text-ink-muted">
        {label ?? ""}
        <CopyButton text={code} className="bg-transparent" />
      </figcaption>
      <pre className="overflow-x-auto p-15 font-mono text-code text-ink">
        <code>{code}</code>
      </pre>
    </figure>
  );
}
