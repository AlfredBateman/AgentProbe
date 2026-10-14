import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Tooltip } from "./tooltip";

function setup() {
  render(
    <Tooltip label="Runs a suite five times per case.">
      <button>Run</button>
    </Tooltip>,
  );
  return { button: screen.getByRole("button", { name: "Run" }), tip: () => screen.getByRole("tooltip", { hidden: true }) };
}

test("the trigger is described by a tooltip that is hidden until hover or focus", () => {
  const { button, tip } = setup();
  expect(button.getAttribute("aria-describedby")).toBe(tip().id);
  expect(tip().hidden).toBe(true);
  expect(tip().textContent).toBe("Runs a suite five times per case.");
});

test("hover shows it and leaving hides it", () => {
  const { button, tip } = setup();
  fireEvent.mouseEnter(button.parentElement!);
  expect(tip().hidden).toBe(false);
  fireEvent.mouseLeave(button.parentElement!);
  expect(tip().hidden).toBe(true);
});

test("keyboard focus shows it, blur hides it, and Escape dismisses it while focused", () => {
  const { button, tip } = setup();
  fireEvent.focus(button);
  expect(tip().hidden).toBe(false);
  fireEvent.keyDown(button, { key: "Escape" });
  expect(tip().hidden).toBe(true);
  fireEvent.blur(button);
  fireEvent.focus(button);
  expect(tip().hidden).toBe(false); // a new focus shows it again
  fireEvent.blur(button);
  expect(tip().hidden).toBe(true);
});

test("Escape with no tooltip open is left alone, so a dialog around it can still close", () => {
  const { button } = setup();
  const notPrevented = fireEvent.keyDown(button, { key: "Escape" });
  expect(notPrevented).toBe(true);
});
