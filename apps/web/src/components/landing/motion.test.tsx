import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import facts from "./facts.json";
import { CountUp, formatFigure, parseFigure } from "./motion";

const { detection, falseAlarms, regression, runsPerCase } = facts;

test("every animated figure formats back to exactly its own text", () => {
  const figures = [
    `${detection.detected} / ${detection.planted}`,
    falseAlarms.shipped,
    runsPerCase,
    regression.baselinePasses,
    regression.candidatePasses,
    regression.passRateBefore,
    regression.passRateAfter,
  ];
  for (const text of figures) {
    const figure = parseFigure(text);
    expect(figure, text).toBeDefined();
    expect(formatFigure(figure!.value, figure!)).toBe(text);
  }
  expect(parseFigure("0.9%")).toEqual({ value: 0.9, decimals: 1, suffix: "%" });
  expect(parseFigure("n/a")).toBeUndefined();
});

test("without motion, a count renders its final figure", () => {
  // The default matchMedia stub matches nothing, so motion is off.
  const { container } = render(
    <p>
      <CountUp value="0.9%" />
    </p>,
  );
  expect(container.textContent).toBe("0.9%");
  expect(container.querySelector("[data-motion]")).toBeNull();
});
