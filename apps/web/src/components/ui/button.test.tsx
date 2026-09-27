import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Button, buttonClasses } from "./button";

test("primary is the white pill with the press shrink", () => {
  render(<Button>Run suite</Button>);
  const button = screen.getByRole("button", { name: "Run suite" });
  expect(button.getAttribute("type")).toBe("button"); // never submits a form by accident
  expect(button.className).toContain("bg-primary");
  expect(button.className).toContain("text-on-primary");
  expect(button.className).toContain("rounded-pill");
  expect(button.className).toContain("active:scale-[0.97]");
  expect(button.className).toContain("min-h-44");
});

test.each([
  ["secondary", "bg-surface-1", "rounded-pill"],
  ["translucent", "bg-surface-2", "rounded-xxl"],
  ["icon", "bg-surface-1", "rounded-full"],
] as const)("%s variant", (variant, surface, radius) => {
  const classes = buttonClasses(variant);
  expect(classes).toContain(surface);
  expect(classes).toContain(radius);
  expect(classes).not.toMatch(/accent-blue/); // blue is a signal, never a fill
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
  expect(buttonClasses("secondary", "w-full")).toMatch(/bg-surface-1.*w-full$/);
});
