"use client";

import gsap from "gsap";
import { SplitText } from "gsap/SplitText";
import { type RefObject, useLayoutEffect } from "react";
import { DURATION, EASE, whenMotionAllowed } from "./core";

gsap.registerPlugin(SplitText);

/**
 * Each line of a heading slides up out of a clipping mask, once, on mount. Kept apart from
 * hooks.ts so SplitText only ships on routes that use it. The split reverts when the reveal
 * ends: the mask would otherwise keep clipping tight display-size descenders. Like useReveal,
 * it removes a server-rendered `data-motion="hidden"` either way. If that guard has already
 * run out (globals.css shows an h1 after 600ms on a slow load), the heading is on screen and
 * is left alone.
 */
export function useSplitHeading<T extends Element>(ref: RefObject<T | null>) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const shown = el.getAttribute("data-motion") === "hidden" && getComputedStyle(el).clipPath === "none";
    el.removeAttribute("data-motion");
    if (shown) return;
    return whenMotionAllowed(el, () => {
      SplitText.create(el, {
        type: "lines",
        mask: "lines",
        autoSplit: true, // re-splits once the web font loads, so lines are measured in the final face
        onSplit: (self) =>
          gsap.from(self.lines, {
            yPercent: 110,
            duration: DURATION.slow,
            ease: EASE.mech,
            stagger: 0.06,
            onComplete: () => self.revert(),
          }),
      });
    });
  }, [ref]);
}
