"use client";

import gsap from "gsap";
import { usePathname } from "next/navigation";
import { type ReactNode, useLayoutEffect, useRef } from "react";
import { DURATION, EASE, HIDDEN, SHOWN, whenMotionAllowed } from "./core";

/**
 * Wraps a route group's content in a clip wipe that plays when the pathname changes, for
 * `(app)/layout.tsx`. A layout does not remount on navigation (a template does, but only when
 * its direct child segment changes, which inside one group is almost never), so this watches
 * `usePathname()` itself and never remounts anything: page state, scroll and focus are kept.
 *
 * Enter only: an exit would mean holding the old route in the tree, which fights streaming.
 * `children` stays a server-rendered slot, so Suspense boundaries inside keep streaming;
 * whatever arrives after the wipe simply appears. The first run of an instance is the page that
 * is already on screen, so it is skipped, and so is a navigation that keeps the pathname (a
 * search-param change). Clip-path only, never a transform, so `position: fixed` descendants
 * keep the viewport as their containing block. No scripts or styles are injected, and the
 * inline style goes through the CSSOM, so the nonce CSP is unaffected.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const shown = useRef<string | null>(null);
  const pathname = usePathname();
  useLayoutEffect(() => {
    const el = ref.current;
    const from = shown.current;
    shown.current = pathname;
    if (!el || from === null || pathname === null || from === pathname) return;
    return whenMotionAllowed(el, () => {
      gsap.fromTo(el, HIDDEN, { ...SHOWN, duration: DURATION.slow, ease: EASE.mech, clearProps: "clipPath" });
    });
  }, [pathname]);
  return <div ref={ref}>{children}</div>;
}
