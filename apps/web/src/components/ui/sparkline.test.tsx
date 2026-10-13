import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Sparkline, sparklinePoints } from "./sparkline";

test("points span the width, and a higher value is higher up", () => {
  const pts = sparklinePoints([0, 5, 10], 100, 30);
  expect(pts.map(([x]) => x)).toEqual([3, 50, 97]);
  expect(pts[0][1]).toBeGreaterThan(pts[1][1]);
  expect(pts[1][1]).toBeGreaterThan(pts[2][1]);
  expect(Math.min(...pts.map(([, y]) => y))).toBe(3); // the maximum touches the padding, not the edge
  expect(Math.max(...pts.map(([, y]) => y))).toBe(27);
});

test("a flat series sits mid-height, and one value sits mid-width", () => {
  expect(sparklinePoints([4, 4, 4], 100, 30).map(([, y]) => y)).toEqual([15, 15, 15]);
  expect(sparklinePoints([4], 100, 30)).toEqual([[50, 15]]);
});

test("non-finite values are skipped, and no values give no points", () => {
  expect(sparklinePoints([1, Number.NaN, Infinity, 3], 100, 30)).toHaveLength(2);
  expect(sparklinePoints([], 100, 30)).toEqual([]);
});

test("a sparkline is an image with a text alternative", () => {
  render(<Sparkline values={[0.9, 0.8, 0.95]} label="Pass rate, last 3 runs: 95%" />);
  expect(screen.getByRole("img", { name: "Pass rate, last 3 runs: 95%" })).toBeTruthy();
});

test("decorative is hidden from assistive technology", () => {
  const { container } = render(<Sparkline values={[1, 2]} decorative />);
  expect(container.querySelector("svg")!.getAttribute("aria-hidden")).toBe("true");
  expect(container.querySelector("[role=img]")).toBeNull();
});

test("it draws a line and a square end marker, or a dashed baseline when empty", () => {
  const { container, rerender } = render(<Sparkline values={[1, 2, 3]} label="x" />);
  expect(container.querySelector("polyline")).not.toBeNull();
  expect(container.querySelector("rect")).not.toBeNull();
  expect(container.querySelector("circle")).toBeNull();
  rerender(<Sparkline values={[]} label="x" />);
  expect(container.querySelector("polyline")).toBeNull();
  expect(container.querySelector("line")!.getAttribute("stroke-dasharray")).not.toBeNull();
});
