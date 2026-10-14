import type { ComponentProps } from "react";
import { cx } from "@/lib/cx";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "icon";

// DESIGN.md buttons: 40px rectangles (44px on coarse pointers), mono caps, no radius. Hover
// inverts or brightens the border; press moves the button down 1px. The focus ring is global.
// Padding and size live in the variants, so a variant never fights the base for a property.
const base =
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-8 border whitespace-nowrap select-none type-button " +
  "transition-[background-color,border-color,color] duration-120 ease-linear active:translate-y-1 motion-reduce:transition-none " +
  "disabled:pointer-events-none disabled:opacity-50";

const text = "min-h-40 px-16 pointer-coarse:min-h-44";
const outline = "border-hairline-strong bg-canvas text-ink hover:border-ink";

const variants: Record<ButtonVariant, string> = {
  // The one lime fill in a view.
  primary: `${text} border-accent bg-accent text-on-accent hover:border-ink hover:bg-ink`,
  secondary: `${text} ${outline}`,
  // Red means destructive; it fills only on hover, when it is about to be pressed.
  danger: `${text} border-fail bg-canvas text-fail hover:bg-fail hover:text-on-fail`,
  ghost: `${text} border-transparent bg-transparent text-ink-muted hover:bg-surface-1 hover:text-ink`,
  icon: `size-40 pointer-coarse:size-44 ${outline}`,
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
