import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/** A loading placeholder; size it with className. Four hard steps, not a shimmer. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cx(
        "bg-surface-2 animate-[skeleton-step_1.2s_steps(4,end)_infinite_alternate] motion-reduce:animate-none",
        className,
      )}
    />
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-8 px-16 py-32">
      <p aria-hidden className="type-micro text-ink-muted">
        {"///"} Empty
      </p>
      <p className="type-headline text-ink">{title}</p>
      {description && <p className="max-w-420 type-body text-ink-muted">{description}</p>}
      {action && <div className="mt-12">{action}</div>}
    </div>
  );
}
