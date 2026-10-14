import gsap from "gsap";
import { CustomEase } from "gsap/CustomEase";

gsap.registerPlugin(CustomEase);

/** DESIGN.md `motion.duration`, in seconds (GSAP's unit). motion.test.tsx keeps them equal to it. */
export const DURATION = { instant: 0.08, fast: 0.12, base: 0.2, slow: 0.4, count: 0.8 } as const;

export const MECH_BEZIER = "0.2,0,0,1";
CustomEase.create("mech", MECH_BEZIER);
/** DESIGN.md `motion.easing`. No springs, no bounce. */
export const EASE = { step: "steps(6)", linear: "none", mech: "mech" } as const;

/** Set on <html> to behave as if the OS asked for reduced motion (the /dev/components switch). */
export const REDUCE_ATTR = "data-reduce-motion";

/** The reveal-in-waiting state that globals.css hides under `[data-motion="hidden"]`. */
export const HIDDEN = { clipPath: "inset(0 0 100% 0)" } as const;
export const SHOWN = { clipPath: "inset(0 0 0% 0)" } as const;

/**
 * Runs `setup` only while motion is allowed, scoped to `scope`. GSAP reverts everything created
 * inside (tweens, inline styles, SplitText) when the query stops matching and on the returned
 * cleanup. Under reduced motion `setup` never runs, so the markup stays in its final state.
 */
export function whenMotionAllowed(scope: Element, setup: () => void | (() => void)) {
  const mm = gsap.matchMedia();
  mm.add(
    "(prefers-reduced-motion: no-preference)",
    () => {
      if (document.documentElement.hasAttribute(REDUCE_ATTR)) return;
      return setup();
    },
    scope,
  );
  return () => mm.revert();
}

/**
 * Calls `play` once, when `el` first scrolls into view. The native observer does this for free;
 * ScrollTrigger would add its own ~12 kB for a play-once need. Without IntersectionObserver
 * (jsdom, very old browsers) it plays at once.
 */
export function whenVisible(el: Element, play: () => void) {
  if (typeof IntersectionObserver === "undefined") {
    play();
    return () => {};
  }
  const observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        observer.disconnect();
        play();
      }
    },
    { rootMargin: "0px 0px -10% 0px" },
  );
  observer.observe(el);
  return () => observer.disconnect();
}
