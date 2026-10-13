"use client";

import gsap from "gsap";
import { type ReactNode, useLayoutEffect, useRef } from "react";
import { DURATION, EASE, HIDDEN, SHOWN, whenMotionAllowed } from "./core";

// The first mount in a tab is the server-rendered page: it is already on screen, so animating
// it would flash it and then wipe it in. Only navigations after that animate. Cleared in a
// microtask so dev StrictMode's synchronous second effect run still sees the first mount.
let firstMount = true;

/**
 * Wraps a route's content in a clip wipe, for `app/template.tsx` (a template remounts on every
 * navigation, a layout does not). Enter only: an exit would mean holding the old route in the
 * tree, which fights streaming. `children` stays a server-rendered slot, so Suspense boundaries
 * inside keep streaming; whatever arrives after the wipe simply appears. Clip-path only, never
 * a transform, so `position: fixed` descendants (dialogs, toasts) keep the viewport as their
 * containing block. No scripts or styles are injected, so the nonce CSP is unaffected.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    const skip = firstMount;
    queueMicrotask(() => {
      firstMount = false;
    });
    if (!el || skip) return;
    return whenMotionAllowed(el, () => {
      gsap.fromTo(el, HIDDEN, { ...SHOWN, duration: DURATION.slow, ease: EASE.mech, clearProps: "clipPath" });
    });
  }, []);
  return <div ref={ref}>{children}</div>;
}
