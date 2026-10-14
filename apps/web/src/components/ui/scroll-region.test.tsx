import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ScrollRegion } from "./scroll-region";

function widths(scroll: number, client: number) {
  vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(scroll);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(client);
}

afterEach(() => vi.restoreAllMocks());

test("a table that fits is a plain box: no region, no hint, no tab stop", () => {
  widths(300, 300);
  const { container } = render(<ScrollRegion label="Cases">table</ScrollRegion>);
  expect(screen.queryByRole("region")).toBeNull();
  expect(container.querySelector("[data-scroll-hint]")).toBeNull();
  expect(container.querySelector("[tabindex]")).toBeNull();
});

test("an overflowing table is a labelled, focusable region with a hint that follows the scroll", () => {
  widths(900, 390);
  const { container } = render(<ScrollRegion label="Cases">table</ScrollRegion>);
  const region = screen.getByRole("region", { name: "Cases, scrolls sideways" });
  expect(region.tabIndex).toBe(0);
  const hint = container.querySelector("[data-scroll-hint]")!;
  const [back, , ahead] = [...hint.children] as HTMLElement[];
  expect(back.className).toContain("invisible"); // at the start: nothing to the left
  expect(ahead.className).not.toContain("invisible");

  vi.spyOn(HTMLElement.prototype, "scrollLeft", "get").mockReturnValue(510);
  fireEvent.scroll(region);
  expect(back.className).not.toContain("invisible");
  expect(ahead.className).toContain("invisible"); // at the end: nothing more to the right
});
