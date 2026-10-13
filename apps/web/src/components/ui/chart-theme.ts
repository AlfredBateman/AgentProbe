import { createElement } from "react";

// Recharts props for the dashboard's charts. Values are CSS variables from theme.css, so there's
// one source of color. Rules (ADR 0042 §6, dataviz method):
// - categorical series take SERIES in this fixed order, never cycled; a fifth folds into "Other";
// - a single series, or the "current" line, is ink; a baseline is dashed ink-muted;
// - lime marks the brand and a selection, so it only leads when a chart has one series that matters;
// - grey steps alone do not separate series: tell them apart by dash pattern and direct labels;
// - pass/fail are never told apart by color alone, so result charts label them.

const v = (name: string) => `var(--color-${name})`;

export const SERIES = [v("chart-1"), v("chart-2"), v("chart-3"), v("chart-4")] as const;
export const CURRENT = v("ink");
export const BASELINE = v("ink-muted");

const tick = { fill: v("ink-muted"), fontSize: 11, fontFamily: "var(--font-mono)" };

/** The hovered point: a square, like every other mark. Recharts passes the point's cx and cy. */
function SquareDot({ cx, cy, stroke }: { cx?: number; cy?: number; stroke?: string }) {
  if (cx === undefined || cy === undefined) return null;
  return createElement("rect", { x: cx - 4, y: cy - 4, width: 8, height: 8, fill: stroke ?? CURRENT, stroke: v("canvas"), strokeWidth: 2 });
}

export const chartTheme = {
  grid: { stroke: v("hairline"), vertical: false },
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
  legend: { wrapperStyle: { fontSize: 11, fontFamily: "var(--font-mono)", color: v("ink-muted") }, iconSize: 8 },
  /** Spread onto <Line>: 2px stroke, no resting dots, a square 8px hover marker. */
  line: {
    strokeWidth: 2,
    dot: false,
    activeDot: SquareDot,
    isAnimationActive: false,
  },
} as const;
