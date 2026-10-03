import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { awakeFetch, resetWake, wakeNotice } from "./wake";

const BASE = "http://localhost:3000";

/**
 * A fake platform in front of the API: /api/health answers with the next outcome in `health`
 * (the last one forever); other requests answer with the next in `api` (default 200).
 */
function fakeApi({ health = [200] as (number | "drop")[], api = [200] as number[] } = {}) {
  const calls: string[] = [];
  let h = 0;
  let a = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | URL) => {
      const req = input instanceof Request ? input : new Request(input);
      const path = new URL(req.url).pathname;
      calls.push(`${req.method} ${path}`);
      if (path === "/api/health") {
        const outcome = health[Math.min(h++, health.length - 1)];
        if (outcome === "drop") throw new TypeError("fetch failed");
        return new Response(null, { status: outcome });
      }
      return new Response(null, { status: api[Math.min(a++, api.length - 1)] });
    }),
  );
  return calls;
}

const get = (path: string) => new Request(BASE + path);
const post = (path: string) => new Request(BASE + path, { method: "POST", body: "{}" });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  resetWake();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("a warm API is probed once, then left alone for minutes", async () => {
  const calls = fakeApi();
  expect((await awakeFetch(get("/api/projects"))).status).toBe(200);
  expect((await awakeFetch(post("/api/projects"))).status).toBe(200);
  expect(calls).toEqual(["GET /api/health", "GET /api/projects", "POST /api/projects"]);
  expect(wakeNotice.get()).toBe(false);
});

test("a cold API: requests wait, with backoff and a notice, then go through once", async () => {
  const calls = fakeApi({ health: ["drop", 502, 504, 200] });
  const seen: boolean[] = [];
  const unsubscribe = wakeNotice.subscribe(() => seen.push(wakeNotice.get()));
  const pending = awakeFetch(post("/api/auth/login"));
  await vi.advanceTimersByTimeAsync(1_000);
  expect(wakeNotice.get()).toBe(false); // no flash for a warm API's quick answer
  await vi.advanceTimersByTimeAsync(1_000);
  expect(wakeNotice.get()).toBe(true);
  expect(calls).toEqual(["GET /api/health", "GET /api/health"]); // 1 s, then 2 s apart
  await vi.advanceTimersByTimeAsync(10_000);
  expect((await pending).status).toBe(200);
  expect(calls).toEqual([...Array(4).fill("GET /api/health"), "POST /api/auth/login"]);
  expect(seen).toEqual([true, false]);
  unsubscribe();
});

test("requests arriving while it wakes share one wake", async () => {
  const calls = fakeApi({ health: [503, 200] });
  const pending = Promise.all([awakeFetch(get("/api/auth/me")), awakeFetch(get("/api/projects"))]);
  await vi.advanceTimersByTimeAsync(2_000);
  expect((await pending).map((r) => r.status)).toEqual([200, 200]);
  expect(calls.filter((c) => c === "GET /api/health")).toHaveLength(2);
});

test("a GET that meets a gateway error after the API fell asleep waits and is retried once", async () => {
  const calls = fakeApi({ api: [200, 502, 200] });
  await awakeFetch(get("/api/projects"));
  const pending = awakeFetch(get("/api/projects"));
  await vi.advanceTimersByTimeAsync(0);
  expect((await pending).status).toBe(200);
  expect(calls).toEqual(["GET /api/health", "GET /api/projects", "GET /api/projects", "GET /api/health", "GET /api/projects"]);
});

test("a mutation is never sent twice: its gateway error is returned as is", async () => {
  const calls = fakeApi({ api: [502] });
  expect((await awakeFetch(post("/api/suites/s1/runs"))).status).toBe(502);
  expect(calls).toEqual(["GET /api/health", "POST /api/suites/s1/runs"]);
});

test("a mutation's dropped connection is thrown, not retried", async () => {
  fakeApi();
  await awakeFetch(get("/api/health-warm-up"));
  vi.mocked(fetch).mockRejectedValueOnce(new TypeError("fetch failed"));
  await expect(awakeFetch(post("/api/projects"))).rejects.toThrow("fetch failed");
});

test("an API that never wakes: after the budget the request goes ahead and fails on its own", async () => {
  const calls = fakeApi({ health: [502], api: [502] });
  const pending = awakeFetch(post("/api/auth/login"));
  await vi.advanceTimersByTimeAsync(156_000); // the 150 s budget, plus the last 5 s backoff
  expect((await pending).status).toBe(502);
  expect(calls.at(-1)).toBe("POST /api/auth/login");
  expect(wakeNotice.get()).toBe(false);
});

test("services the proxy can't wake get one direct, opaque ping per 10 minutes", async () => {
  const sent: { url: string; mode?: RequestMode }[] = [];
  let woken = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | URL | string, init?: RequestInit) => {
      const url = input instanceof Request ? input.url : input.toString();
      sent.push({ url, mode: init?.mode });
      if (url === "https://api.example/health") {
        woken = true; // a direct request wakes it
        return new Response(null, { status: 200 });
      }
      if (url.endsWith("/api/health")) return new Response(null, { status: woken ? 200 : 502 }); // "no-deploy"
      return new Response(null, { status: 200 });
    }),
  );
  const urls = ["https://api.example/health", "https://agents.example/health"];
  const first = awakeFetch(get("/api/projects"), urls);
  await vi.advanceTimersByTimeAsync(10_000);
  expect((await first).status).toBe(200);
  const direct = () => sent.filter((s) => !s.url.startsWith(BASE));
  expect(direct()).toEqual(urls.map((url) => ({ url, mode: "no-cors" })));

  await vi.advanceTimersByTimeAsync(9 * 60_000);
  await awakeFetch(get("/api/projects"), urls);
  expect(direct()).toHaveLength(2); // not again within 10 minutes
  await vi.advanceTimersByTimeAsync(60_000);
  await awakeFetch(get("/api/projects"), urls);
  expect(direct()).toHaveLength(4);
});

test("without nudge URLs nothing is sent outside /api", async () => {
  const calls = fakeApi({ health: [502, 502, 200] });
  const pending = awakeFetch(get("/api/projects"), []);
  await vi.advanceTimersByTimeAsync(10_000);
  expect((await pending).status).toBe(200);
  expect(calls.every((c) => c.includes(" /api/"))).toBe(true);
});
