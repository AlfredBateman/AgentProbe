import { cx } from "@/lib/cx";

export type Status = "pass" | "fail" | "flaky" | "error" | "stable";

const LABELS: Record<Status, string> = {
  pass: "Pass",
  fail: "Fail",
  flaky: "Flaky",
  error: "Error",
  stable: "Stable",
};

const TEXT: Record<Status, string> = {
  pass: "text-pass",
  fail: "text-fail",
  flaky: "text-flaky",
  error: "text-neutral",
  stable: "text-ink",
};

// Pass green and fail red are indistinguishable to deuteranopes (ADR 0028), so each status
// also has its own shape: circle, diamond, half-filled circle, ring, bar.
const SHAPE: Record<Status, string> = {
  pass: "size-8 rounded-full bg-current",
  fail: "size-8 rotate-45 scale-90 rounded-[1px] bg-current",
  flaky: "size-8 rounded-full border-[1.5px] border-current bg-[linear-gradient(90deg,currentColor_50%,transparent_50%)]",
  error: "size-8 rounded-full border-[1.5px] border-current",
  stable: "h-2 w-8 rounded-full bg-current",
};

type DotProps = { status: Status; className?: string } & (
  | { label: string; decorative?: never }
  | { label?: never; decorative: true }
);

/** An 8px status mark. Standalone it needs a label; inside labelled text, mark it decorative. */
export function StatusDot({ status, label, decorative, className }: DotProps) {
  return (
    <span
      className={cx("inline-block shrink-0", TEXT[status], SHAPE[status], className)}
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": label, title: label })}
    />
  );
}

/** DESIGN.md badge-*: status-colored label on surface-2. The text is always there, never color alone. */
export function Badge({ status, children, className }: { status: Status; children?: string; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-6 rounded-sm bg-surface-2 px-8 py-2 text-data-label whitespace-nowrap",
        TEXT[status],
        className,
      )}
    >
      <StatusDot status={status} decorative />
      {children ?? LABELS[status]}
    </span>
  );
}
