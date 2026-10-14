import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Pagination, pageWindow } from "./pagination";

test.each([
  [1, 1, [1]],
  [1, 3, [1, 2, 3]],
  [1, 12, [1, 2, "gap", 12]],
  [6, 12, [1, "gap", 5, 6, 7, "gap", 12]],
  [12, 12, [1, "gap", 11, 12]],
  [3, 5, [1, 2, 3, 4, 5]],
] as const)("window for page %i of %i", (page, count, expected) => {
  expect(pageWindow(page, count)).toEqual(expected);
});

test("a labelled nav with the current page marked", () => {
  render(<Pagination page={6} pageCount={12} onPageChange={() => {}} label="Runs pages" />);
  expect(screen.getByRole("navigation", { name: "Runs pages" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Page 6" }).getAttribute("aria-current")).toBe("page");
  expect(screen.getByRole("button", { name: "Page 5" }).getAttribute("aria-current")).toBeNull();
});

test("page buttons, previous and next report the new page", () => {
  const onPageChange = vi.fn();
  render(<Pagination page={6} pageCount={12} onPageChange={onPageChange} />);
  fireEvent.click(screen.getByRole("button", { name: "Page 7" }));
  fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(onPageChange.mock.calls.map(([p]) => p)).toEqual([7, 5, 7]);
});

test("previous is disabled on the first page and next on the last, so neither can be focused", () => {
  const { rerender } = render(<Pagination page={1} pageCount={3} onPageChange={() => {}} />);
  expect((screen.getByRole("button", { name: "Previous page" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Next page" }) as HTMLButtonElement).disabled).toBe(false);
  rerender(<Pagination page={3} pageCount={3} onPageChange={() => {}} />);
  expect((screen.getByRole("button", { name: "Next page" }) as HTMLButtonElement).disabled).toBe(true);
});

test("an out-of-range page is clamped, and the skipped runs are hidden from assistive technology", () => {
  const { container } = render(<Pagination page={99} pageCount={12} onPageChange={() => {}} />);
  expect(screen.getByRole("button", { name: "Page 12" }).getAttribute("aria-current")).toBe("page");
  expect(container.querySelector("li[aria-hidden]")!.textContent).toBe("…");
});
