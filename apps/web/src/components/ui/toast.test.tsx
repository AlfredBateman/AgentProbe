import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ToastProvider, useToast } from "./toast";

function Trigger() {
  const toast = useToast();
  return <button onClick={() => toast({ title: "Run started", tone: "pass" })}>go</button>;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("a toast appears in the live region and dismisses itself after 5 s", () => {
  render(
    <ToastProvider>
      <Trigger />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByText("go"));
  const toast = screen.getByRole("status");
  expect(toast.textContent).toContain("Run started");
  expect(toast.parentElement!.getAttribute("aria-live")).toBe("polite");
  act(() => vi.advanceTimersByTime(4999));
  expect(screen.queryByRole("status")).not.toBeNull();
  act(() => vi.advanceTimersByTime(1));
  expect(screen.queryByRole("status")).toBeNull();
});

test("the dismiss button closes a toast", () => {
  render(
    <ToastProvider>
      <Trigger />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByText("go"));
  fireEvent.click(screen.getByText("go"));
  expect(screen.getAllByRole("status")).toHaveLength(2);
  fireEvent.click(screen.getAllByRole("button", { name: "Dismiss" })[0]);
  expect(screen.getAllByRole("status")).toHaveLength(1);
});

test("useToast outside a provider fails loudly", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => render(<Trigger />)).toThrow(/ToastProvider/);
});
