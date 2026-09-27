import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Card } from "./card";
import { GradientCard } from "./gradient-card";

test("Card lifts one surface step and renders a panel header", () => {
  const { container, rerender } = render(<Card>body</Card>);
  expect(container.firstElementChild!.className).toContain("bg-surface-1");
  rerender(
    <Card lifted title="Latest runs" actions={<button>View all</button>}>
      body
    </Card>,
  );
  expect(container.firstElementChild!.className).toContain("bg-surface-2");
  expect(screen.getByRole("heading", { name: "Latest runs" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "View all" })).toBeTruthy();
});

afterEach(() => vi.restoreAllMocks());

test("a second GradientCard warns; one alone does not", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  const first = render(<GradientCard>one</GradientCard>);
  expect(warn).not.toHaveBeenCalled();
  render(<GradientCard>two</GradientCard>);
  expect(warn).toHaveBeenCalledTimes(1);
  first.unmount();
  warn.mockClear();
  render(<GradientCard>three</GradientCard>); // two mounted again
  expect(warn).toHaveBeenCalledTimes(1);
});
