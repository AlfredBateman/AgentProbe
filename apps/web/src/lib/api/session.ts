// Session refresh for cookie auth (ADR 0009, ADR 0029). Both tokens are httpOnly cookies, so
// this code never sees a token. It only decides when to call /auth/refresh, and it must call
// it exactly once per expiry: presenting an already-rotated refresh token counts as theft and
// revokes every session the user has.

const LOCK = "agentprobe-session-refresh";
// A 401 from these means bad credentials or a dead session, not an expired access cookie.
const NO_REFRESH = new Set(["/api/auth/login", "/api/auth/register", "/api/auth/refresh", "/api/auth/logout"]);

/**
 * A fetch that, on a 401, refreshes the session once and retries the request once.
 * - Concurrent 401s in a tab share one refresh.
 * - Across tabs, a Web Lock serializes refreshes, and a probe of /auth/me inside the lock
 *   skips the refresh when another tab already rotated the cookies.
 * - login/register/refresh/logout pass through untouched; a retry that still fails is returned as is.
 *
 * `send` makes the requests themselves (lib/api/wake.ts's awakeFetch in the app).
 */
export function createSessionFetch(onExpired: () => void, send: (request: Request) => Promise<Response> = (r) => fetch(r)) {
  let inflight: Promise<boolean> | null = null;

  async function refresh(base: string): Promise<boolean> {
    const run = async () => {
      if ((await fetch(new URL("/api/auth/me", base))).ok) return true; // another tab refreshed
      return (await fetch(new URL("/api/auth/refresh", base), { method: "POST" })).ok;
    };
    const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
    const ok = locks ? await locks.request(LOCK, run) : await run();
    if (!ok) onExpired();
    return ok;
  }

  return async function sessionFetch(request: Request): Promise<Response> {
    const retry = request.clone(); // the body can only be read once
    const response = await send(request);
    if (response.status !== 401 || NO_REFRESH.has(new URL(request.url).pathname)) return response;
    inflight ??= refresh(request.url).finally(() => {
      inflight = null;
    });
    return (await inflight) ? send(retry) : response;
  };
}
