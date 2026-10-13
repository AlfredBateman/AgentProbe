import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Button, buttonClasses } from "./button";

test("primary is the one lime fill, a 40px rectangle that moves down 1px when pressed", () => {
  render(<Button>Run suite</Button>);
  const button = screen.getByRole("button", { name: "Run suite" });
  expect(button.getAttribute("type")).toBe("button"); // never submits a form by accident
  expect(button.className).toContain("bg-accent");
  expect(button.className).toContain("text-on-accent");
  expect(button.className).toContain("active:translate-y-1");
  expect(button.className).toContain("min-h-40");
  expect(button.className).toContain("pointer-coarse:min-h-44");
});

test.each([
  ["secondary", "border-hairline-strong", "bg-canvas"],
  ["danger", "border-fail", "text-fail"],
  ["ghost", "border-transparent", "bg-transparent"],
  ["translucent", "border-hairline-strong", "bg-canvas"], // the legacy name is the secondary outline
  ["icon", "border-hairline-strong", "size-40"],
] as const)("%s variant", (variant, ...expected) => {
  const classes = buttonClasses(variant);
  for (const c of expected) expect(classes).toContain(c);
  expect(classes).not.toContain("bg-accent"); // a lime fill is the primary action only
  expect(classes).not.toMatch(/rounded|shadow|gradient/);
});

test("red is only ever the danger variant", () => {
  for (const variant of ["primary", "secondary", "ghost", "translucent", "icon"] as const) {
    expect(buttonClasses(variant)).not.toContain("fail");
  }
});

test("a button is a native, focusable control and a disabled one leaves the tab order", () => {
  render(
    <>
      <Button>Start</Button>
      <Button disabled>Wait</Button>
    </>,
  );
  const [start, wait] = screen.getAllByRole("button");
  start.focus();
  expect(document.activeElement).toBe(start);
  expect(start.tabIndex).toBe(0);
  wait.focus();
  expect(document.activeElement).not.toBe(wait);
  expect((wait as HTMLButtonElement).disabled).toBe(true);
});

test("icon buttons are named and submit when asked", () => {
  render(
    <Button variant="icon" aria-label="Close" type="submit">
      x
    </Button>,
  );
  expect(screen.getByRole("button", { name: "Close" }).getAttribute("type")).toBe("submit");
});

test("buttonClasses lets a link look like a button", () => {
  expect(buttonClasses("secondary", "w-full")).toMatch(/bg-canvas.*w-full$/);
});
