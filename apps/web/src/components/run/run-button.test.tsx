import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { awakeFetch, resetWake } from "@/lib/api/wake";
import { RunButton } from "./run-button";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  resetWake();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** An API that answers 502 until `awake()` is called. */
function sleepingApi() {
  let up = false;
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: up ? 200 : 502 })));
  return { awake: () => (up = true) };
}
// A POST: a GET that meets a gateway error waits for the API a second time, which this isn't about.
const request = () => awakeFetch(new Request("http://localhost:3000/api/projects", { method: "POST" }));

test("a run starts on click when nothing is in the way", () => {
  const onClick = vi.fn();
  render(<RunButton onClick={onClick} />);
  const button = screen.getByRole("button", { name: "Run" });
  expect((button as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(button);
  expect(onClick).toHaveBeenCalledOnce();
});

test("while the API wakes the button is disabled and says why, then unlocks when it answers", async () => {
  const api = sleepingApi();
  render(<RunButton onClick={() => {}} />);
  const pending = request();
  await act(() => vi.advanceTimersByTimeAsync(2_000));

  const button = screen.getByRole("button", { name: "Waking…" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  const reason = screen.getByRole("status");
  expect(reason.textContent).toContain("about 30 to 40 seconds");
  expect(button.getAttribute("aria-describedby")).toBe(reason.id);

  api.awake();
  await act(() => vi.advanceTimersByTimeAsync(5_000));
  await pending;
  expect((screen.getByRole("button", { name: "Run" }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getByRole("status").textContent).toBe("");
});

test("an API that never answered keeps the button disabled, with the way out", async () => {
  sleepingApi();
  render(<RunButton onClick={() => {}} />);
  const pending = request();
  await act(() => vi.advanceTimersByTimeAsync(160_000));
  await pending;

  expect((screen.getByRole("button", { name: "Run" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("status").textContent).toContain("Reload the page");
});

test("a reason from the page disables the run; in a table row it stays for assistive technology only", () => {
  const { rerender } = render(<RunButton onClick={() => {}} blocked="Add a suite to run first." />);
  const button = screen.getByRole("button", { name: "Run" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(screen.getByText("Add a suite to run first.").className).not.toContain("sr-only");

  rerender(<RunButton onClick={() => {}} blocked="Add a suite to run first." note={false} />);
  expect(screen.getByText("Add a suite to run first.").className).toContain("sr-only");
});

test("the label and look are the caller's", () => {
  render(<RunButton variant="secondary" label="Run a suite" onClick={() => {}} data-testid="go" />);
  const button = screen.getByTestId("go");
  expect(button.textContent).toBe("Run a suite");
  expect(button.className).toContain("border-hairline-strong");
});
