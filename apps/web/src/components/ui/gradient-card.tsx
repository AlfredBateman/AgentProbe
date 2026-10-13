"use client";

import { type HTMLAttributes, useEffect } from "react";
import { cx } from "@/lib/cx";

let mounted = 0;

/**
 * The page's one emphasized panel: flat, with a 2px accent border (DESIGN.md allows no
 * gradient; the name is from before ADR 0042). At most one per viewport; a second one warns
 * in development.
 */
export function GradientCard({ className, ...props }: HTMLAttributes<HTMLElement>) {
  useEffect(() => {
    mounted += 1;
    if (mounted > 1 && process.env.NODE_ENV !== "production") {
      console.warn("GradientCard: more than one is mounted; DESIGN.md allows one per viewport.");
    }
    return () => {
      mounted -= 1;
    };
  }, []);

  return <section className={cx("border-2 border-accent bg-surface-1 p-32 text-subhead text-ink", className)} {...props} />;
}
