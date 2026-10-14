import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { resetWake } from "@/lib/api/wake";
import { StatusChip } from "./status-chip";

beforeEach(resetWake);
afterEach(() => vi.unstubAllGlobals());

test("it says checking, then online once /api/health answers", async () => {
  const paths: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | URL) => {
      paths.push(new URL(input instanceof Request ? input.url : input).pathname);
      return new Response(null, { status: 200 });
    }),
  );
  render(<StatusChip />);
  expect(screen.getByRole("status").textContent).toBe("API checking");
  expect(await screen.findByText("API online")).toBeTruthy();
  expect(paths).toContain("/api/health");
});

test("an API that answers with an error is unreachable, with the error mark and no red", async () => {
  // The wake probe passes, then the request itself fails.
  const answers = [200, 500];
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: answers.shift() ?? 500 })));
  render(<StatusChip />);
  const chip = (await screen.findByText("API unreachable")).closest("span")!;
  expect(chip.querySelector(".mark-error")).not.toBeNull();
  expect(chip.className).not.toContain("text-fail");
});
