import { createElement } from "react";

// Recharts props for the overview's trend charts, on DESIGN.md's chart rules: mono axis labels,
// 1px strokes, flat fills, square markers, no colour fade. Values are CSS variables from
// theme.css, so there's one source of colour. A single series is ink; a baseline is dashed
// ink-muted; a second series is ink-muted and dashed too, and is named in the legend.

const v = (name: string) => `var(--color-${name})`;

export const CURRENT = v("ink");
export const BASELINE = v("ink-muted");

const tick = { fill: v("ink-muted"), fontSize: 11, fontFamily: "var(--font-mono)" };

/** A point: a square, like every other mark. Recharts passes the point's cx and cy. */
export function SquareDot({ cx, cy, stroke }: { cx?: number; cy?: number; stroke?: string }) {
  if (cx === undefined || cy === undefined) return null;
  return createElement("rect", { x: cx - 4, y: cy - 4, width: 8, height: 8, fill: stroke ?? CURRENT, stroke: v("canvas"), strokeWidth: 1 });
}

/** Below this many runs a line says little: every point gets its marker. */
export const SPARSE_RUNS = 3;

export const chartTheme = {
  grid: { stroke: v("hairline"), strokeWidth: 1, vertical: false },
  xAxis: { tick, axisLine: false, tickLine: false, tickMargin: 8 },
  yAxis: { tick, axisLine: false, tickLine: false, width: 40 },
  tooltip: {
    cursor: { stroke: v("hairline-strong"), strokeWidth: 1 },
    contentStyle: {
      background: v("surface-2"),
      border: `1px solid ${v("hairline-strong")}`,
      fontSize: 12,
      fontFamily: "var(--font-mono)",
      color: v("ink"),
    },
    labelStyle: { color: v("ink-muted") },
    itemStyle: { color: v("ink") },
  },
  /** Spread onto <Line>: a 1px stroke, no resting dots, a square hover marker. */
  line: {
    strokeWidth: 1,
    dot: false,
    activeDot: SquareDot,
    isAnimationActive: false,
  },
} as const;

/** A line's resting markers: every point while there are too few runs to read a line. */
export const restingDots = (count: number) => (count < SPARSE_RUNS ? SquareDot : false);
