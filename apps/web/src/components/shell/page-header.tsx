"use client";

import { type ReactNode, useRef } from "react";
import { useReveal } from "@/lib/motion/hooks";

/**
 * A page's title strip (DESIGN.md Layout): a micro eyebrow, the display title, and the page's
 * actions on the right, over a 1px strong rule. It clips in once on load.
 *
 * `verbatim`: the title is data the user wrote (a suite name), so it keeps its case and wraps
 * anywhere instead of being uppercased by the display tier.
 */
export function PageHeader({
  eyebrow,
  title,
  verbatim,
  actions,
  children,
}: {
  eyebrow: ReactNode;
  title: string;
  verbatim?: boolean;
  actions?: ReactNode;
  /** Under the title: a metadata line. */
  children?: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  useReveal(ref);
  return (
    <header ref={ref} className="flex flex-wrap items-end justify-between gap-x-16 gap-y-12 border-b border-hairline-strong pb-16">
      <div className="min-w-0">
        <p className="type-micro text-ink-muted [&_a]:tap">{eyebrow}</p>
        <h1 className={verbatim ? "mt-8 type-display-md normal-case break-words" : "mt-8 type-display-md"}>{title}</h1>
        {children && <div className="mt-8">{children}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-start gap-8">{actions}</div>}
    </header>
  );
}
