import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { awakeFetch, resetWake } from "@/lib/api/wake";
import { WakingNotice } from "./waking-notice";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  resetWake();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("the notice shows in a live region while the API wakes, and goes once it answers", async () => {
  let awake = false;
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: awake ? 200 : 502 })));
  render(<WakingNotice />);
  const region = screen.getByRole("status");
  expect(region.getAttribute("aria-live")).toBe("polite");
  expect(region.textContent).toBe("");

  const pending = awakeFetch(new Request("http://localhost:3000/api/projects"));
  await act(() => vi.advanceTimersByTimeAsync(2_000));
  expect(region.textContent).toContain("Waking the server, about 30 to 40 seconds");

  awake = true;
  await act(() => vi.advanceTimersByTimeAsync(5_000));
  expect((await pending).status).toBe(200);
  expect(region.textContent).toBe("");
});
