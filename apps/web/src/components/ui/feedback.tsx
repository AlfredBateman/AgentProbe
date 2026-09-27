import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/** A loading placeholder; size it with className. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-md bg-hairline motion-reduce:animate-none", className)} />;
}

export function EmptyState({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-8 px-20 py-40 text-center">
      <p className="font-display text-dash-heading text-ink">{title}</p>
      {description && <p className="max-w-420 text-body text-ink-muted">{description}</p>}
      {action && <div className="mt-12">{action}</div>}
    </div>
  );
}
