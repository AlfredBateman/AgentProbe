import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { CodeBlock, CopyButton } from "./code";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function stubClipboard(writeText: (text: string) => Promise<void>) {
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
}

test("untrusted output renders as literal text, never as HTML", () => {
  const payload = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
  const { container } = render(<CodeBlock code={payload} label="output" />);
  expect(container.querySelector("img, script")).toBeNull();
  expect(container.querySelector("code")!.textContent).toBe(payload);
});

test("copy succeeds, announces, and resets after 2 s", async () => {
  vi.useFakeTimers();
  const writeText = vi.fn(() => Promise.resolve());
  stubClipboard(writeText);
  render(<CopyButton text="ap_example" />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
  expect(writeText).toHaveBeenCalledWith("ap_example");
  expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
  expect(screen.getByText("Copied", { selector: "[aria-live]" })).toBeTruthy();
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
});

test("a rejected or missing clipboard says so", async () => {
  stubClipboard(() => Promise.reject(new Error("denied")));
  render(<CopyButton text="x" />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy" })));
  expect(screen.getByRole("button", { name: "Copy failed" })).toBeTruthy();
});
