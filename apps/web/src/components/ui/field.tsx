import type { ComponentProps, ReactNode } from "react";
import { cx } from "@/lib/cx";
import { ChevronDownIcon } from "./icons";

// DESIGN.md text-input: canvas, a hairline-strong border, mono text as written (never
// uppercased: what is typed is data). Invalid is a red border; pair it with `FieldError`.
const control =
  "w-full border border-hairline-strong bg-canvas px-12 type-code text-ink placeholder:text-ink-muted hover:border-ink " +
  "aria-invalid:border-fail aria-invalid:hover:border-fail disabled:cursor-not-allowed disabled:opacity-50";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cx(control, "h-40 pointer-coarse:h-44", className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cx(control, "min-h-96 resize-y py-8", className)} {...props} />;
}

/** A native select: keyboard, screen reader and mobile pickers for free. */
export function Select({ className, ...props }: ComponentProps<"select">) {
  return (
    <span className={cx("relative inline-flex", className)}>
      <select className={cx(control, "h-40 cursor-pointer appearance-none pr-36 pointer-coarse:h-44")} {...props} />
      <ChevronDownIcon className="pointer-events-none absolute top-1/2 right-12 -translate-y-1/2 text-ink-muted" />
    </span>
  );
}

// A native checkbox, so the keyboard, form submission and screen readers need nothing extra.
// Checked is an ink square inside the box: lime is never a fill on a control.
const box =
  "size-18 shrink-0 cursor-pointer appearance-none border border-hairline-strong bg-transparent p-3 bg-clip-content " +
  "hover:border-ink checked:border-ink checked:bg-ink aria-invalid:border-fail disabled:cursor-not-allowed disabled:opacity-50";

export function Checkbox({ className, ...props }: Omit<ComponentProps<"input">, "type">) {
  return <input type="checkbox" className={cx(box, className)} {...props} />;
}

// A checkbox with the switch role. The thumb slides, so on and off differ by position and not
// by colour alone.
const track =
  "relative h-20 w-40 shrink-0 cursor-pointer appearance-none border border-hairline-strong bg-canvas " +
  "before:absolute before:top-3 before:left-3 before:size-12 before:bg-ink-muted before:transition-transform before:duration-120 before:ease-linear " +
  "hover:border-ink checked:border-ink checked:before:translate-x-20 checked:before:bg-ink disabled:cursor-not-allowed disabled:opacity-50";

export function Switch({ className, ...props }: Omit<ComponentProps<"input">, "type" | "role">) {
  return <input type="checkbox" role="switch" className={cx(track, className)} {...props} />;
}

/** A field label in mono caps. `caption` is a small note after it: a unit, "optional". */
export function Label({ caption, className, children, ...props }: ComponentProps<"label"> & { caption?: ReactNode }) {
  return (
    <label className={cx("type-label text-ink-muted", className)} {...props}>
      {children}
      {caption && <span className="ml-8 type-micro">{caption}</span>}
    </label>
  );
}

/** DESIGN.md's error state: fail-colored sentence, linked to its input by id. Pair the id with
 * `aria-describedby` on the input, which also gets `aria-invalid`. */
export function FieldError({ id, children }: { id: string; children?: string | null }) {
  if (!children) return null;
  return (
    <p id={id} className="type-body-sm text-fail">
      {children}
    </p>
  );
}

/** A form-level failure (a bad password, a rate limit, a server error): bordered and announced
 * as it appears, since it belongs to no single field. */
export function FormError({ id, children }: { id: string; children?: string | null }) {
  if (!children) return null;
  return (
    <p id={id} role="alert" className="border border-fail p-12 type-body-sm text-fail">
      {children}
    </p>
  );
}
