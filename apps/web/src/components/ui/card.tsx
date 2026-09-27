import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "@/lib/cx";

type Props = Omit<HTMLAttributes<HTMLElement>, "title"> & {
  /** One surface step up (surface-2), DESIGN.md's "featured" lift. */
  lifted?: boolean;
  title?: ReactNode;
  actions?: ReactNode;
};

/** A surface-1 card; with a title it is a panel with a header row. */
export function Card({ lifted, title, actions, className, children, ...props }: Props) {
  return (
    <section
      className={cx("min-w-0 rounded-xl p-24", lifted ? "bg-surface-2" : "bg-surface-1", className)}
      {...props}
    >
      {(title || actions) && (
        <header className="mb-15 flex flex-wrap items-center justify-between gap-12">
          {title && <h2 className="font-display text-dash-heading">{title}</h2>}
          {actions && <div className="flex items-center gap-8">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
