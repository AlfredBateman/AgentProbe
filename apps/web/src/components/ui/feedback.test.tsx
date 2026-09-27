import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { EmptyState, Skeleton } from "./feedback";

test("Skeleton is hidden from assistive tech and stops pulsing under reduced motion", () => {
  const { container } = render(<Skeleton className="h-20 w-120" />);
  const el = container.firstElementChild!;
  expect(el.getAttribute("aria-hidden")).toBe("true");
  expect(el.className).toContain("motion-reduce:animate-none");
  expect(el.className).toContain("h-20 w-120");
});

test("EmptyState renders its slots", () => {
  render(<EmptyState title="No runs yet" description="Start one from a suite." action={<button>New run</button>} />);
  expect(screen.getByText("No runs yet")).toBeTruthy();
  expect(screen.getByText("Start one from a suite.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "New run" })).toBeTruthy();
});
