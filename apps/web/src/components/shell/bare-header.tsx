import Link from "next/link";
import type { ReactNode } from "react";

/** The wordmark on its own, for pages outside a project (auth, projects list). */
export function BareHeader({ right }: { right?: ReactNode }) {
  return (
    <header className="flex h-56 shrink-0 items-center justify-between px-16 tablet:px-30">
      <Link
        href="/"
        className="font-display text-[20px] font-medium tracking-[-0.6px] text-ink outline-none focus-visible:shadow-focus"
      >
        AgentProbe
      </Link>
      {right}
    </header>
  );
}
