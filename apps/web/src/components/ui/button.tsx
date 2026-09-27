import type { ComponentProps } from "react";
import { cx } from "@/lib/cx";

export type ButtonVariant = "primary" | "secondary" | "translucent" | "icon";

// Press is a scale shrink, not a darker fill (DESIGN.md button-primary-pressed).
const base =
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-6 whitespace-nowrap text-button select-none " +
  "transition-transform duration-100 active:scale-[0.97] motion-reduce:transition-none motion-reduce:active:scale-100 " +
  "outline-none focus-visible:shadow-focus disabled:pointer-events-none disabled:opacity-50";

const variants: Record<ButtonVariant, string> = {
  primary: "min-h-44 rounded-pill bg-primary px-15 py-10 text-on-primary",
  secondary: "min-h-44 rounded-pill bg-surface-1 px-15 py-10 text-ink",
  translucent: "min-h-40 rounded-xxl bg-surface-2 px-14 py-8 text-ink",
  icon: "size-40 rounded-full bg-surface-1 text-ink pointer-coarse:size-44",
};

/** Classes for anything that should look like a button, e.g. a next/link. */
export function buttonClasses(variant: ButtonVariant = "primary", className?: string) {
  return cx(base, variants[variant], className);
}

type Props = ComponentProps<"button"> &
  // An icon button has no text, so it must be named.
  ({ variant?: Exclude<ButtonVariant, "icon"> } | { variant: "icon"; "aria-label": string });

export function Button({ variant = "primary", className, type = "button", ...props }: Props) {
  return <button type={type} className={buttonClasses(variant, className)} {...props} />;
}
