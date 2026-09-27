import { afterEach, expect, test, vi } from "vitest";
import { createSessionFetch } from "./session";

const BASE = "http://localhost:3000";

/** A fake API: every non-auth request is 401 until a refresh succeeds. */
function fakeApi({ refreshStatus = 204, refreshRevives = true } = {}) {
  const state = { valid: false, refreshes: 0, calls: [] as string[] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : new Request(input, init);
      const path = new URL(req.url).pathname;
      state.calls.push(`${req.method} ${path}`);
      await new Promise((r) => setTimeout(r, 1)); // let concurrent requests interleave
      if (path === "/api/auth/refresh") {
        state.refreshes += 1;
        if (refreshStatus === 204 && refreshRevives) state.valid = true;
        return new Response(null, { status: refreshStatus });
      }
      if (!state.valid) return new Response(null, { status: 401 });
      return Response.json({ path, body: await req.text() });
    }),
  );
  return state;
}

/** A Web Lock stand-in: callbacks for one name run one at a time, like navigator.locks. */
function fakeLocks() {
  let tail: Promise<unknown> = Promise.resolve();
  const locks = {
    held: [] as string[],
    request: (name: string, callback: () => Promise<unknown>) => {
      locks.held.push(name);
      const result = tail.then(callback);
      tail = result.catch(() => {});
      return result;
    },
  };
  Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
  return locks;
}

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "locks");
});

const get = (path: string) => new Request(BASE + path);

test("concurrent 401s trigger exactly one refresh, and every request is retried", async () => {
  const api = fakeApi();
  const onExpired = vi.fn();
  const sessionFetch = createSessionFetch(onExpired);
  const responses = await Promise.all([1, 2, 3, 4, 5].map((i) => sessionFetch(get(`/api/projects/${i}`))));
  expect(responses.map((r) => r.status)).toEqual([200, 200, 200, 200, 200]);
  expect(api.refreshes).toBe(1);
  expect(onExpired).not.toHaveBeenCalled();
});

test("two tabs expiring together refresh once: the second sees the first's cookies", async () => {
  const api = fakeApi();
  const locks = fakeLocks();
  const tabA = createSessionFetch(vi.fn());
  const tabB = createSessionFetch(vi.fn());
  const [a, b] = await Promise.all([tabA(get("/api/projects")), tabB(get("/api/projects"))]);
  expect([a.status, b.status]).toEqual([200, 200]);
  expect(api.refreshes).toBe(1); // a second refresh would reuse a rotated token and revoke everything
  expect(locks.held).toEqual(["agentprobe-session-refresh", "agentprobe-session-refresh"]);
});

test("no refresh when the probe finds the session already fresh", async () => {
  const api = fakeApi();
  const sessionFetch = createSessionFetch(vi.fn());
  const first = sessionFetch(get("/api/projects"));
  await new Promise((r) => setTimeout(r, 0));
  api.valid = true; // another tab refreshed while this request was in flight
  expect((await first).status).toBe(200);
  expect(api.refreshes).toBe(0);
});

test("a failed refresh reports expiry once and returns the 401s", async () => {
  const api = fakeApi({ refreshStatus: 401 });
  const onExpired = vi.fn();
  const sessionFetch = createSessionFetch(onExpired);
  const responses = await Promise.all([sessionFetch(get("/api/a")), sessionFetch(get("/api/b"))]);
  expect(responses.map((r) => r.status)).toEqual([401, 401]);
  expect(api.refreshes).toBe(1);
  expect(onExpired).toHaveBeenCalledTimes(1);
});

test("a retry that still fails is returned without a second refresh", async () => {
  const api = fakeApi({ refreshRevives: false });
  const response = await createSessionFetch(vi.fn())(get("/api/projects"));
  expect(response.status).toBe(401);
  expect(api.refreshes).toBe(1);
});

test("auth endpoints pass through: a bad login is not a reason to refresh", async () => {
  const api = fakeApi();
  const login = new Request(BASE + "/api/auth/login", { method: "POST", body: "{}" });
  // The fake returns 401 for everything but refresh while signed out.
  expect((await createSessionFetch(vi.fn())(login)).status).toBe(401);
  expect(api.refreshes).toBe(0);
  expect(api.calls).toEqual(["POST /api/auth/login"]);
});

test("an expired session on /auth/me is refreshed like any other request", async () => {
  const api = fakeApi();
  const response = await createSessionFetch(vi.fn())(get("/api/auth/me"));
  expect(response.status).toBe(200);
  expect(api.refreshes).toBe(1);
});

test("a POST body survives the retry", async () => {
  fakeApi();
  const body = JSON.stringify({ name: "support-bot" });
  const request = new Request(BASE + "/api/projects", { method: "POST", body, headers: { "Content-Type": "application/json" } });
  const response = await createSessionFetch(vi.fn())(request);
  expect(await response.json()).toEqual({ path: "/api/projects", body });
});
