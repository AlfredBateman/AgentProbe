"use client";

// Motion hooks (DESIGN.md Motion): reveals clip or translate, numbers count up once, and under
// prefers-reduced-motion nothing is animated, so the markup is already in its final state.
// Every hook animates transform and clip-path only, clears them when done (no will-change is
// ever set), and cleans up through the gsap.matchMedia context in core.ts.
import gsap from "gsap";
import { type RefObject, useEffectEvent, useLayoutEffect, useRef } from "react";
import { DURATION, EASE, HIDDEN, SHOWN, whenMotionAllowed, whenVisible } from "./core";

/** Rows past this many are off screen or not worth a tween each; they just appear. */
const MAX_STAGGERED = 40;

/** Starts `targets` clipped, plays them in when `el` is first visible. Returns the cleanup. */
function revealWhenVisible(el: Element, targets: Element[], vars: gsap.TweenVars, from: gsap.TweenVars = {}) {
  const tween = gsap.fromTo(targets, { ...HIDDEN, ...from }, { ...SHOWN, ...vars, paused: true, clearProps: "clipPath,transform" });
  return whenVisible(el, () => tween.play());
}

/**
 * A clip reveal of `ref`'s element, once, when it scrolls into view. Put
 * `data-motion="hidden"` on a server-rendered element to keep it from showing its end state
 * before hydration; the hook removes it either way.
 */
export function useReveal<T extends Element>(ref: RefObject<T | null>, { delay = 0 } = {}) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.removeAttribute("data-motion");
    return whenMotionAllowed(el, () => revealWhenVisible(el, [el], { duration: DURATION.base, ease: EASE.mech, delay }));
  }, [ref, delay]);
}

/**
 * Rows of a list or table reveal one after another (the first 40, over at most 400 ms in all).
 * Animates `selector` inside `ref`, or its direct children, e.g. `"tbody tr"`.
 */
export function useStagger<T extends Element>(ref: RefObject<T | null>, selector?: string) {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.removeAttribute("data-motion");
    return whenMotionAllowed(el, () => {
      const rows = Array.from(selector ? el.querySelectorAll(selector) : el.children).slice(0, MAX_STAGGERED);
      if (!rows.length) return;
      return revealWhenVisible(
        el,
        rows,
        { y: 0, duration: DURATION.base, ease: EASE.mech, stagger: { amount: Math.min(rows.length * 0.03, DURATION.slow) } },
        { y: 8 },
      );
    });
  }, [ref, selector]);
}

/**
 * Counts `ref`'s text from zero to `value`, once, when it scrolls into view. Render the returned
 * text as the element's only child: `<span ref={ref}>{text}</span>`. React keeps owning that
 * text node, so a later value change just shows the new text. `format` need not be stable.
 */
export function useCountUp<T extends Element>(ref: RefObject<T | null>, value: number, format: (n: number) => string = String) {
  const text = format(value);
  const latest = useEffectEvent(() => ({ value, text, format }));
  useLayoutEffect(() => {
    const el = ref.current;
    const node = el?.firstChild;
    if (!el || !(node instanceof Text)) return;
    return whenMotionAllowed(el, () => {
      const counter = { n: 0 };
      node.nodeValue = latest().format(0);
      const tween = gsap.to(counter, {
        n: latest().value,
        duration: DURATION.count,
        ease: EASE.mech,
        paused: true,
        onUpdate: () => {
          node.nodeValue = latest().format(counter.n);
        },
        onComplete: () => {
          node.nodeValue = latest().text;
        },
      });
      const stop = whenVisible(el, () => tween.play());
      return () => {
        stop();
        node.nodeValue = latest().text;
      };
    });
  }, [ref]);
  return text;
}

/**
 * One stepped flash when `key` changes after mount (a run board cell changing state): `ref`'s
 * element, hidden by its own class, is shown and clipped away again in three hard steps. Never
 * on mount, so a page that loads a finished board doesn't flash every cell at once; never under
 * reduced motion. A change mid-flash restarts it.
 */
export function useFlash<T extends Element>(ref: RefObject<T | null>, key: string) {
  const last = useRef(key);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || last.current === key) return;
    last.current = key;
    return whenMotionAllowed(el, () => {
      gsap.fromTo(el, SHOWN, { ...HIDDEN, duration: DURATION.slow, ease: "steps(3)", clearProps: "clipPath" });
    });
  }, [ref, key]);
}
