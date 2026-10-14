import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Stat, StatGrid } from "./stat";

test("a stat pairs a label with its value as a description list", () => {
  const { container } = render(<Stat label="Pass rate" value="86.7%" note="CI 80.1 to 92.0" />);
  expect(container.querySelector("dl > dt")!.textContent).toBe("Pass rate");
  expect(screen.getByText("86.7%").className).toContain("type-display-lg");
  expect(screen.getByText("CI 80.1 to 92.0").tagName).toBe("DD");
});

test("a failing figure is red; a leader line is decoration", () => {
  const { container } = render(<Stat label="Regressed" value="01" tone="fail" leader />);
  expect(screen.getByText("01").className).toContain("text-fail");
  expect(container.querySelector("[aria-hidden]")).not.toBeNull();
});

test("without a tone, a value is plain ink and has no leader", () => {
  const { container } = render(<Stat label="Cases" value="30" />);
  expect(screen.getByText("30").className).not.toContain("text-fail");
  expect(container.querySelector("[aria-hidden]")).toBeNull();
});

test("a grid of stats is divided by 1px lines and goes two-up on narrow screens", () => {
  const { container } = render(
    <StatGrid>
      <Stat label="A" value="1" />
      <Stat label="B" value="2" />
    </StatGrid>,
  );
  expect(container.firstElementChild!.className).toContain("grid-lines");
  expect(container.firstElementChild!.className).toContain("grid-cols-2");
});
