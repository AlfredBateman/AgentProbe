import Link from "next/link";
import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "@/lib/cx";
import { ArrowUpRightIcon } from "./icons";

type Props = Omit<HTMLAttributes<HTMLElement>, "title"> & {
  /** panel-raised: one surface step up, with the strong edge. */
  lifted?: boolean;
  title?: ReactNode;
  /** The title in `headline` (default) or in `label`, for a dense panel. */
  titleStyle?: "headline" | "label";
  /** Metadata or actions, right-aligned in the header strip. */
  actions?: ReactNode;
  /** Makes the whole panel one link, carried by the title (so it needs one), with the corner arrow. */
  href?: string;
  /** "+" marks on two corners. */
  crosshair?: boolean;
};

/** DESIGN.md panel: a bordered compartment. With a title it has a header strip, a line under it. */
export function Panel({ lifted, title, titleStyle = "headline", actions, href, crosshair, className, children, ...props }: Props) {
  const heading = titleStyle === "label" ? "type-label text-ink-muted" : "type-headline";
  return (
    <section
      className={cx(
        "min-w-0 border p-16",
        lifted ? "border-hairline-strong bg-surface-1" : "border-hairline bg-canvas",
        href && "relative hover:border-ink",
        crosshair && "crosshair",
        className,
      )}
      {...props}
    >
      {(title || actions) && (
        <header className="mb-16 -mx-16 -mt-16 flex min-h-40 flex-wrap items-center justify-between gap-x-12 gap-y-4 border-b border-hairline px-16 py-8">
          {title && (
            <h2 className={heading}>
              {href ? (
                // A stretched link: its ::after covers the panel, so the whole panel is one target.
                <Link href={href} className="text-ink no-underline after:absolute after:inset-0">
                  {title}
                </Link>
              ) : (
                title
              )}
            </h2>
          )}
          {(actions || href) && (
            <div className="relative z-(--z-raised) ml-auto flex items-center gap-8">
              {actions}
              {href && <ArrowUpRightIcon aria-hidden className="text-ink-muted" />}
            </div>
          )}
        </header>
      )}
      {children}
    </section>
  );
}
