import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { awakeFetch, resetWake } from "@/lib/api/wake";
import { ServicesChip } from "./services-chip";

afterEach(() => {
  resetWake();
  vi.unstubAllGlobals();
});

const stubFetch = () => {
  const fetchMock = vi.fn<(input: Request | URL) => Promise<Response>>(async () => new Response(null, { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

test("a chip that is not told to probe sends nothing and shows Checking", () => {
  const fetchMock = stubFetch();
  render(<ServicesChip />);
  expect(screen.getByText("Checking")).toBeTruthy();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("a probing chip asks the API once and then reads Awake", async () => {
  const fetchMock = stubFetch();
  render(<ServicesChip probe />);
  await waitFor(() => expect(screen.getByText("Awake")).toBeTruthy());
  const asked = fetchMock.mock.calls.map(([r]) => new URL(r instanceof Request ? r.url : String(r)).pathname);
  expect(asked.filter((p) => p === "/api/health").length).toBeGreaterThan(0);
  expect(asked.every((p) => p === "/api/health")).toBe(true);
});

test("a probing chip adds no request when something has already answered", async () => {
  const fetchMock = stubFetch();
  await awakeFetch(new Request("http://localhost/api/projects"), []);
  const before = fetchMock.mock.calls.length;
  render(<ServicesChip probe />);
  expect(screen.getByText("Awake")).toBeTruthy();
  expect(fetchMock.mock.calls.length).toBe(before);
});
