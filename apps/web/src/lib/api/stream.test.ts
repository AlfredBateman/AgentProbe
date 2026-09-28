import { beforeEach, expect, test, vi } from "vitest";
import { api } from "./client";
import { streamUrl } from "./stream";

vi.mock("./client", () => ({ api: { POST: vi.fn() } }));
const post = vi.mocked(api.POST);

beforeEach(() => post.mockReset());

test("with a public API URL, each call mints a stream token and targets the API directly", async () => {
  let n = 0;
  post.mockImplementation((async () => ({ data: { token: `a b/${++n}`, expires_in: 60 } })) as never);
  expect(await streamUrl("run 1", "https://api.example.test/")).toBe("https://api.example.test/runs/run%201/stream?token=a%20b%2F1");
  expect(await streamUrl("run 1", "https://api.example.test")).toBe("https://api.example.test/runs/run%201/stream?token=a%20b%2F2");
  expect(post).toHaveBeenCalledTimes(2);
  expect(post.mock.calls[0]).toEqual(["/runs/{run_id}/stream-token", { params: { path: { run_id: "run 1" } } }]);
});

test("without one it uses the /api rewrite, and a refused token is an error", async () => {
  expect(await streamUrl("r1", "")).toBe("/api/runs/r1/stream");
  expect(post).not.toHaveBeenCalled();
  post.mockResolvedValue({ data: undefined, error: { error: { message: "Run not found" } } } as never);
  await expect(streamUrl("r1", "https://api.example.test")).rejects.toThrow("stream token");
});
