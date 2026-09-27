// Recharts props for the dashboard's charts. Values are CSS variables from theme.css, so there's
// one source of color. Rules (ADR 0028, dataviz method):
// - categorical series take SERIES in this fixed order, never cycled; a fifth folds into "Other";
// - a single series, or the "current" line, is ink; a baseline is dashed ink-muted;
// - accent-blue is never a series (it means links, focus and selection);
// - pass/fail are never told apart by color alone (deuteranopes can't), so result charts label them.

const v = (name: string) => `var(--color-${name})`;

/** Validated with the dataviz palette checker against canvas, surface-1 and surface-2. */
export const SERIES = [v("chart-1"), v("chart-2"), v("chart-3"), v("chart-4")] as const;
export const CURRENT = v("ink");
export const BASELINE = v("ink-muted");

const tick = { fill: v("ink-muted"), fontSize: 12 };

export const chartTheme = {
  grid: { stroke: v("hairline-soft"), vertical: false },
  xAxis: { tick, axisLine: false, tickLine: false, tickMargin: 8 },
  yAxis: { tick, axisLine: false, tickLine: false, width: 40 },
  tooltip: {
    cursor: { stroke: v("hairline"), strokeWidth: 1 },
    contentStyle: {
      background: v("surface-2"),
      border: `1px solid ${v("hairline")}`,
      borderRadius: 10,
      fontSize: 13,
      color: v("ink"),
    },
    labelStyle: { color: v("ink-muted") },
    itemStyle: { color: v("ink") },
  },
  legend: { wrapperStyle: { fontSize: 12, color: v("ink-muted") }, iconSize: 8 },
  /** Spread onto <Line>: 2px stroke, no resting dots, an 8px hover marker ringed in the surface. */
  line: {
    strokeWidth: 2,
    dot: false,
    activeDot: { r: 4, strokeWidth: 2, stroke: v("surface-1") },
    isAnimationActive: false,
  },
} as const;
