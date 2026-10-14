import Link from "next/link";
import type { ReactNode } from "react";
import { ServicesChip } from "./services-chip";

/**
 * The wordmark and the API status, for pages outside the shell (auth, errors). The chip is
 * there because these are the pages a visitor meets while the API is still waking.
 */
export function BareHeader({
  right,
  chipFromTablet,
}: {
  right?: ReactNode;
  /** Leave the chip out below 810px, where an action beside it does not fit. */
  chipFromTablet?: boolean;
}) {
  return (
    <header className="flex h-56 shrink-0 items-center justify-between gap-12 border-b border-hairline-strong px-16 tablet:px-32">
      <Link href="/" className="tap type-headline text-ink no-underline">
        AgentProbe
        <span aria-hidden className="text-accent">
          ®
        </span>
      </Link>
      <div className="flex items-center gap-12">
        <ServicesChip probe className={chipFromTablet ? "hidden tablet:inline" : undefined} />
        {right}
      </div>
    </header>
  );
}
