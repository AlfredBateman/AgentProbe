"use client";

// The landing page's motion, as small client islands over the server-rendered page. Each one
// renders the same element and text the static page had; lib/motion does the animating, and
// under reduced motion none of it runs. Props are plain strings: they cross from server code.
import { type HTMLAttributes, type ReactNode, useLayoutEffect, useRef } from "react";
import { useCountUp, useReveal, useStagger } from "@/lib/motion/hooks";
import { useSplitHeading } from "@/lib/motion/split-heading";

type Figure = { value: number; decimals: number; suffix: string };

/** A figure's leading number and what follows it: "0.9%" is 0.9, 1 decimal, "%"; "9 / 9" is 9, " / 9". */
export function parseFigure(text: string): Figure | undefined {
  const m = /^(\d+)(?:\.(\d+))?(.*)$/.exec(text);
  return m ? { value: Number(`${m[1]}.${m[2] ?? 0}`), decimals: m[2]?.length ?? 0, suffix: m[3] } : undefined;
}

export const formatFigure = (n: number, { decimals, suffix }: Figure) => n.toFixed(decimals) + suffix;

/** The h1, its lines sliding up out of a mask once on load. */
export function SplitHeading(props: { id: string; className: string; children: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useSplitHeading(ref);
  return <h1 ref={ref} data-motion="hidden" {...props} />;
}

/** `value`'s leading number counts up from zero once, when it scrolls into view. */
export function CountUp({ value }: { value: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const figure = parseFigure(value);
  const text = useCountUp(ref, figure?.value ?? 0, (n) => (figure ? formatFigure(n, figure) : value));
  // Hidden until the count has reset the text to zero, so the final number never flashes first.
  useLayoutEffect(() => ref.current?.removeAttribute("data-motion"), []);
  return (
    <span ref={ref} data-motion="hidden" className="inline-block">
      {text}
    </span>
  );
}

type Box = HTMLAttributes<HTMLElement> & { as: "section" | "article" | "div" };

/** A panel that clips in once, when it scrolls into view. */
export function Reveal({ as: Tag, ...props }: Box) {
  // A div ref types against every tag in the union; all three are plain HTMLElements.
  const ref = useRef<HTMLDivElement>(null);
  useReveal(ref);
  return <Tag ref={ref} data-motion="hidden" {...props} />;
}

/** A row of panels that clip in one after another, once, when the row scrolls into view. */
export function Stagger({ as: Tag, ...props }: Box) {
  const ref = useRef<HTMLDivElement>(null);
  useStagger(ref);
  return <Tag ref={ref} data-motion="hidden" {...props} />;
}
