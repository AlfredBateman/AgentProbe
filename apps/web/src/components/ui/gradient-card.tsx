"use client";

import { type HTMLAttributes, useEffect } from "react";
import { cx } from "@/lib/cx";

/**
 * Violet only: white text fails WCAG AA on the magenta, orange and coral anchors (ADR 0028).
 * The second stop is darker, so contrast only improves across the card.
 */
export const GRADIENT_STOPS = ["#6a4cf5", "#3b2799"] as const;

let mounted = 0;

/** DESIGN.md gradient spotlight card. At most one per viewport; a second one warns in development. */
export function GradientCard({ className, style, ...props }: HTMLAttributes<HTMLElement>) {
  useEffect(() => {
    mounted += 1;
    if (mounted > 1 && process.env.NODE_ENV !== "production") {
      console.warn("GradientCard: more than one is mounted; DESIGN.md allows one per viewport.");
    }
    return () => {
      mounted -= 1;
    };
  }, []);

  return (
    <section
      className={cx("rounded-xxl p-32 text-subhead text-ink", className)}
      style={{ backgroundImage: `linear-gradient(135deg, ${GRADIENT_STOPS[0]}, ${GRADIENT_STOPS[1]})`, ...style }}
      {...props}
    />
  );
}
