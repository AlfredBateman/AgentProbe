import { render } from "@testing-library/react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { expect, test } from "vitest";
import { BASELINE, chartTheme, CURRENT, SERIES } from "./chart-theme";

test("series are the validated chart tokens in order; blue is never a series", () => {
  expect(SERIES).toEqual(["var(--color-chart-1)", "var(--color-chart-2)", "var(--color-chart-3)", "var(--color-chart-4)"]);
  expect(JSON.stringify({ SERIES, CURRENT, BASELINE, chartTheme })).not.toContain("accent-blue");
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
      <Line dataKey="current" stroke={CURRENT} {...chartTheme.line} />
      <Line dataKey="baseline" stroke={BASELINE} strokeDasharray="4 4" {...chartTheme.line} />
    </LineChart>,
  );
  const strokes = [...container.querySelectorAll("path.recharts-curve")].map((p) => p.getAttribute("stroke"));
  expect(strokes).toEqual([CURRENT, BASELINE]);
});
