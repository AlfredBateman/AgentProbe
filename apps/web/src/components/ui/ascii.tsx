import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

const FRAMES = { square: ["[", "]"], angle: ["<", ">"] } as const;

/** `[ RUNS ]`: ASCII brackets around a word, for the active item or a section mark. The
 * brackets are drawing; assistive technology reads only the word. */
export function AsciiFrame({ children, kind = "square", className }: { children: ReactNode; kind?: keyof typeof FRAMES; className?: string }) {
  const [open, close] = FRAMES[kind];
  return (
    <span className={cx("type-label", className)}>
      <span aria-hidden>{open} </span>
      {children}
      <span aria-hidden> {close}</span>
    </span>
  );
}

/** A "+" registration mark. For a corner of a frame use the `crosshair` utility or `<Panel crosshair>`;
 * this one sits inline, at a grid intersection or beside a figure. */
export function Crosshair({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cx("inline-block type-micro text-ink-muted select-none", className)}>
      +
    </span>
  );
}
