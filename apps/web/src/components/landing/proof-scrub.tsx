"use client";

import gsap from "gsap";
import { useLayoutEffect, useRef } from "react";
import { EASE, whenMotionAllowed } from "@/lib/motion/core";
import { formatFigure, parseFigure } from "./motion";

/**
 * A figure in the proof card that steps from its baseline value to its candidate value as the
 * card scrolls through the viewport, and back when scrolled up. ScrollTrigger is imported here,
 * dynamically, so it ships only to the landing page and only where motion is allowed; until it
 * arrives the figure shows the baseline. Without motion it is the candidate value, as rendered.
 */
export function ScrubValue({ from, to }: { from: string; to: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    const node = el?.firstChild;
    const card = el?.closest("article");
    const [start, end] = [parseFigure(from), parseFigure(to)];
    if (!el || !(node instanceof Text) || !card || !start || !end) return;
    return whenMotionAllowed(el, () => {
      const step = gsap.parseEase(EASE.step); // DESIGN.md's steps(6): the value ticks, it does not glide
      const show = (progress: number) => {
        node.nodeValue = progress >= 1 ? to : formatFigure(start.value + (end.value - start.value) * step(progress), end);
      };
      show(0);
      let trigger: { kill: () => void } | undefined;
      let gone = false;
      import("gsap/ScrollTrigger")
        .then(({ ScrollTrigger }) => {
          if (gone) return;
          gsap.registerPlugin(ScrollTrigger);
          trigger = ScrollTrigger.create({
            trigger: card,
            start: "top 75%",
            end: "top 25%", // from the card's top edge, not its bottom: on a phone the card is taller than the screen
            onUpdate: (self) => show(self.progress),
            onRefresh: (self) => show(self.progress),
          });
        })
        .catch(() => show(1));
      return () => {
        gone = true;
        trigger?.kill();
        node.nodeValue = to;
      };
    });
  }, [from, to]);
  return <span ref={ref}>{to}</span>;
}
