"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { cx } from "@/lib/cx";

type Edge = "none" | "start" | "middle" | "end";

/**
 * A sideways-scrolling box for a table that can be wider than its panel. While its content
 * overflows it is a labelled, focusable region (arrow keys scroll it) with a visible hint
 * that says which way the hidden columns are; when everything fits, it is a plain box.
 */
export function ScrollRegion({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState<Edge>("none");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const max = el.scrollWidth - el.clientWidth;
      if (max <= 1) setEdge("none");
      else if (el.scrollLeft <= 1) setEdge("start");
      else if (el.scrollLeft >= max - 1) setEdge("end");
      else setEdge("middle");
    };
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const sizes = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    sizes?.observe(el);
    if (el.firstElementChild) sizes?.observe(el.firstElementChild);
    return () => {
      el.removeEventListener("scroll", measure);
      sizes?.disconnect();
    };
  }, []);

  const scrolls = edge !== "none";
  return (
    <div className="min-w-0">
      {scrolls && (
        <p data-scroll-hint className="flex justify-between gap-8 border-b border-hairline bg-surface-1 px-12 py-4 type-micro text-ink-muted">
          <span aria-hidden={edge === "start"} className={cx(edge === "start" && "invisible")}>
            ← More
          </span>
          <span>Scroll sideways</span>
          <span aria-hidden={edge === "end"} className={cx(edge === "end" && "invisible")}>
            More →
          </span>
        </p>
      )}
      <div
        ref={ref}
        role={scrolls ? "region" : undefined}
        aria-label={scrolls ? `${label}, scrolls sideways` : undefined}
        tabIndex={scrolls ? 0 : undefined}
        // relative: an absolutely positioned descendant (an sr-only note, say) is held and
        // clipped here instead of widening the page from wherever the table puts it.
        className={cx("relative min-w-0 overflow-x-auto focus-visible:-outline-offset-2", className)}
      >
        {children}
      </div>
    </div>
  );
}
