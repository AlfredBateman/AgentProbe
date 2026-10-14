import { render } from "@testing-library/react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { expect, test } from "vitest";
import { BASELINE, chartTheme, CURRENT, restingDots, SquareDot } from "./chart-theme";

test("telemetry style: 1px strokes, mono ticks, ink and ink-muted only", () => {
  expect(chartTheme.line.strokeWidth).toBe(1);
  expect(chartTheme.grid.strokeWidth).toBe(1);
  expect(chartTheme.xAxis.tick.fontFamily).toBe("var(--font-mono)");
  expect([CURRENT, BASELINE]).toEqual(["var(--color-ink)", "var(--color-ink-muted)"]);
  expect(JSON.stringify(chartTheme)).not.toMatch(/chart-\d|gradient|accent/);
});

test("fewer than three runs get a square marker on every point", () => {
  expect(restingDots(1)).toBe(SquareDot);
  expect(restingDots(2)).toBe(SquareDot);
  expect(restingDots(3)).toBe(false);
});

test("a themed line chart renders its lines with the theme's colors", () => {
  const data = [
    { day: "Mon", current: 0.9, baseline: 0.95 },
    { day: "Tue", current: 0.8, baseline: 0.95 },
  ];
  const { container } = render(
    <LineChart width={400} height={200} data={data}>
      <CartesianGrid {...chartTheme.grid} />
      <XAxis dataKey="day" {...chartTheme.xAxis} />
      <YAxis {...chartTheme.yAxis} />
      <Line dataKey="current" stroke={CURRENT} {...chartTheme.line} dot={restingDots(data.length)} />
      <Line dataKey="baseline" stroke={BASELINE} strokeDasharray="4 4" {...chartTheme.line} />
    </LineChart>,
  );
  const curves = [...container.querySelectorAll("path.recharts-curve")];
  expect(curves.map((p) => p.getAttribute("stroke"))).toEqual([CURRENT, BASELINE]);
  expect(curves.map((p) => p.getAttribute("stroke-width"))).toEqual(["1", "1"]);
  expect(container.querySelectorAll(".recharts-line-dots rect")).toHaveLength(2); // square markers on the sparse line
});
