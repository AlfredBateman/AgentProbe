"use client";

import { type KeyboardEvent, useRef } from "react";
import { cx } from "@/lib/cx";

export type TabItem<V extends string> = { value: V; label: string };

type Props<V extends string> = {
  items: TabItem<V>[];
  value: V;
  onValueChange: (value: V) => void;
  "aria-label": string;
  className?: string;
};

/**
 * DESIGN.md pricing-tab pill toggle: selected = surface lift, not color.
 * WAI-ARIA tabs with a roving tabindex; panels are the caller's (use `tabId(value)` as their label).
 */
export function Tabs<V extends string>({ items, value, onValueChange, className, ...aria }: Props<V>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent, index: number) {
    const last = items.length - 1;
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: last }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    const target = (next + items.length) % items.length;
    onValueChange(items[target].value);
    refs.current[target]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={aria["aria-label"]}
      className={cx("inline-flex max-w-full gap-4 overflow-x-auto rounded-pill bg-canvas p-4", className)}
    >
      {items.map((item, i) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={tabId(item.value)}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onValueChange(item.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cx(
              "min-h-40 shrink-0 cursor-pointer rounded-pill px-14 py-8 text-button outline-none transition-colors focus-visible:shadow-focus",
              selected ? "bg-surface-2 text-ink" : "text-ink-muted hover:text-ink",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

export const tabId = (value: string) => `tab-${value}`;
