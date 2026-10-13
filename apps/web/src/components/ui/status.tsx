import { cx } from "@/lib/cx";

export type Status = "pass" | "fail" | "flaky" | "error" | "stable" | "running" | "queued" | "quarantined";

// DESIGN.md "Status encoding": a status is never told by colour alone. Each has its own 10px
// mark, a shape that reads in greyscale, a chip border, and always its text label. Red is only
// ever fail; every other status is ink or ink-muted.
const STATUS: Record<Status, { label: string; text: string; chip: string; mark: string }> = {
  pass: { label: "Pass", text: "text-ink", chip: "border-hairline-strong", mark: "size-10 bg-current" },
  fail: { label: "Fail", text: "text-fail", chip: "border-fail", mark: "size-10 mark-fail" },
  flaky: { label: "Flaky", text: "text-ink", chip: "border-dashed border-ink", mark: "size-10 hatch" },
  error: { label: "Error", text: "text-ink-muted", chip: "border-hairline-strong", mark: "size-10 mark-error" },
  stable: { label: "Stable", text: "text-ink", chip: "border-hairline-strong", mark: "h-2 w-10 bg-current" },
  running: { label: "Running", text: "text-ink", chip: "border-ink", mark: "size-10 mark-running" },
  queued: { label: "Queued", text: "text-ink-muted", chip: "border-hairline-strong", mark: "w-10 mark-queued" },
  quarantined: { label: "Quarantined", text: "text-ink-muted", chip: "border-dotted border-hairline-strong", mark: "size-10 mark-quarantined" },
};

type DotProps = { status: Status; className?: string } & (
  | { label: string; decorative?: never }
  | { label?: never; decorative: true }
);

/** A 10px status mark. Standalone it needs a label; inside labelled text, mark it decorative. */
export function StatusDot({ status, label, decorative, className }: DotProps) {
  return (
    <span
      className={cx("inline-block shrink-0", STATUS[status].text, STATUS[status].mark, className)}
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": label, title: label })}
    />
  );
}

/** DESIGN.md chip-*: a bordered canvas chip with the mark and the word. The text is always there. */
export function Badge({ status, children, className }: { status: Status; children?: string; className?: string }) {
  const s = STATUS[status];
  return (
    <span className={cx("inline-flex items-center gap-6 border bg-canvas px-8 py-3 type-label whitespace-nowrap", s.chip, s.text, className)}>
      <StatusDot status={status} decorative />
      {children ?? s.label}
    </span>
  );
}
