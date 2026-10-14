"use client";

import { cloneElement, type KeyboardEvent, type ReactElement, useId, useState } from "react";
import { cx } from "@/lib/cx";

type Props = {
  /** What the tooltip says: one short sentence. */
  label: string;
  /** One element that can take `aria-describedby`: a button, a link, an input. */
  children: ReactElement<{ "aria-describedby"?: string }>;
  className?: string;
};

/**
 * A description on hover and on keyboard focus, linked to its trigger with aria-describedby.
 * WCAG 1.4.13: it is hoverable (it sits inside the wrapper), persistent, and Escape dismisses it.
 */
export function Tooltip({ label, children, className }: Props) {
  const id = useId();
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const open = (hover || focus) && !dismissed;

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape" && open) {
      e.preventDefault();
      setDismissed(true);
    }
  }

  return (
    <span
      className={cx("relative inline-flex", className)}
      onMouseEnter={() => {
        setHover(true);
        setDismissed(false);
      }}
      onMouseLeave={() => setHover(false)}
      onFocus={() => {
        setFocus(true);
        setDismissed(false);
      }}
      onBlur={() => setFocus(false)}
      onKeyDown={onKeyDown}
    >
      {cloneElement(children, { "aria-describedby": id })}
      <span
        id={id}
        role="tooltip"
        hidden={!open}
        className="absolute bottom-full left-0 z-(--z-overlay) mb-6 w-max max-w-240 border border-hairline-strong bg-surface-2 px-8 py-4 type-body-sm text-ink"
      >
        {label}
      </span>
    </span>
  );
}
