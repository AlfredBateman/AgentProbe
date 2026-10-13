import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { AsciiFrame, Crosshair } from "./ascii";

test("the frame's brackets are drawing; the word is the content", () => {
  const { container } = render(<AsciiFrame>Runs</AsciiFrame>);
  expect(container.textContent).toBe("[ Runs ]");
  expect([...container.querySelectorAll("[aria-hidden]")].map((el) => el.textContent?.trim())).toEqual(["[", "]"]);
  expect(screen.getByText("Runs").getAttribute("aria-hidden")).toBeNull();
});

test("an angle frame uses angle brackets", () => {
  const { container } = render(<AsciiFrame kind="angle">Re-ind</AsciiFrame>);
  expect(container.textContent).toBe("< Re-ind >");
});

test("a crosshair is a hidden plus", () => {
  const { container } = render(<Crosshair />);
  const mark = container.firstElementChild!;
  expect(mark.textContent).toBe("+");
  expect(mark.getAttribute("aria-hidden")).toBe("true");
});
