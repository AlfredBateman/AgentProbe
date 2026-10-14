import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

type Props = {
  label: string;
  value: ReactNode;
  /** A micro-type footnote under the value. */
  note?: ReactNode;
  /** Red, for a failing figure. */
  tone?: "fail";
  /** A hairline running from the value to the edge of the tile. */
  leader?: boolean;
  className?: string;
};

/** DESIGN.md stat-tile: a mono label, a display-size value, a micro note. Put tiles in a `StatGrid`. */
export function Stat({ label, value, note, tone, leader, className }: Props) {
  return (
    <dl className={cx("flex min-w-0 flex-col gap-12 p-16", className)}>
      <dt className="type-label text-ink-muted">{label}</dt>
      <dd className="flex items-center gap-12">
        <span className={cx("type-display-lg tabular-nums", tone === "fail" && "text-fail")}>{value}</span>
        {leader && <span aria-hidden className="h-px min-w-16 flex-1 bg-ink-muted" />}
      </dd>
      {note && <dd className="type-micro text-ink-muted">{note}</dd>}
    </dl>
  );
}

/** A row of tiles divided by 1px lines; two-up below 810px. Set the columns with `className`. */
export function StatGrid({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("grid-lines grid-cols-2 border border-hairline tablet:grid-cols-4", className)} {...props} />;
}
