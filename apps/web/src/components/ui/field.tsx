import type { ComponentProps } from "react";
import { cx } from "@/lib/cx";
import { ChevronDownIcon } from "./icons";

// DESIGN.md text-input, plus a hairline border (DESIGN.md doesn't need one on its own
// canvas-only pages, but surface-1 is invisible against a surface-1 card or dialog without it).
// aria-invalid gives the error state DESIGN.md leaves open (ADR 0028).
const control =
  "w-full rounded-md border border-hairline bg-surface-1 px-14 py-10 text-body text-ink placeholder:text-ink-muted " +
  "outline-none focus-visible:shadow-focus aria-invalid:border-fail disabled:opacity-50";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cx(control, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cx(control, "min-h-96 resize-y", className)} {...props} />;
}

/** A native select: keyboard, screen reader and mobile pickers for free. */
export function Select({ className, ...props }: ComponentProps<"select">) {
  return (
    <span className={cx("relative inline-flex", className)}>
      <select className={cx(control, "cursor-pointer appearance-none pr-36")} {...props} />
      <ChevronDownIcon className="pointer-events-none absolute top-1/2 right-14 -translate-y-1/2 text-ink-muted" />
    </span>
  );
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cx("text-data-label text-ink-muted", className)} {...props} />;
}

/** DESIGN.md's error state (ADR 0028 §5): fail-colored text, linked to its input by id. Pair
 * the id with `aria-describedby` on the input, which also gets `aria-invalid`. */
export function FieldError({ id, children }: { id: string; children?: string | null }) {
  if (!children) return null;
  return (
    <p id={id} className="text-data-label text-fail">
      {children}
    </p>
  );
}
