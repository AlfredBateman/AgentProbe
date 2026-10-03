import { NUDGE_URLS } from "./public-url";

// A cold API (ADR 0036). On the free tier the API sleeps after about 15 idle minutes and takes
// about 30 to 40 seconds to wake. While it does, requests through /api hang or fail with a
// gateway error, which is not the user's problem to see as one: every API call waits here until
// /api/health answers, and the app shows a "waking the server" notice (WakingNotice) meanwhile.
//
// A request through the web app's proxy doesn't always wake a sleeping Render service: from
// Vercel's Mumbai edge, and from the API to the demo agents, Render answered 502 "no-deploy"
// for minutes instead (measured 2026-10-03), while a request straight from a browser wakes it.
// So the browser also pings each service's /health directly (NUDGE_URLS), at most every 10
// minutes. The pings are opaque (no-cors): only their arrival matters.

const ASLEEP_AFTER_MS = 10 * 60_000; // re-check before calling an API quiet this long
const WAKE_BUDGET_MS = 150_000; // then give up; the request goes ahead and fails on its own
const PROBE_TIMEOUT_MS = 30_000; // a probe the platform holds this long is retried
const NOTICE_AFTER_MS = 1_500; // a warm API answers well within this: no notice flash
const GATEWAY = new Set([502, 503, 504]);
const IDEMPOTENT = new Set(["GET", "HEAD"]);
const NUDGE_EVERY_MS = 10 * 60_000;

let lastAnswer = 0; // when the API last answered (any status but a gateway error)
let lastNudge: number | null = null;
let waking: Promise<void> | null = null;
let showNotice = false;
const listeners = new Set<() => void>();

function setNotice(value: boolean) {
  if (showNotice === value) return;
  showNotice = value;
  listeners.forEach((l) => l());
}

/** For useSyncExternalStore: whether the "waking the server" notice should show. */
export const wakeNotice = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => void listeners.delete(listener);
  },
  get: () => showNotice,
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Polls /api/health with backoff (1, 2, 4, then every 5 s) until it answers. */
async function wake(base: string): Promise<void> {
  const deadline = Date.now() + WAKE_BUDGET_MS;
  const notice = setTimeout(() => setNotice(true), NOTICE_AFTER_MS);
  try {
    for (let attempt = 0; Date.now() < deadline; attempt++) {
      try {
        const r = await fetch(new URL("/api/health", base), { cache: "no-store", signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
        if (r.ok) {
          lastAnswer = Date.now();
          return;
        }
      } catch {
        // the platform dropped or held the request: still waking
      }
      await sleep(Math.min(1000 * 2 ** attempt, 5000));
    }
  } finally {
    clearTimeout(notice);
    setNotice(false);
  }
}

function nudge(urls: string[]) {
  if (lastNudge !== null && Date.now() - lastNudge < NUDGE_EVERY_MS) return;
  lastNudge = Date.now();
  for (const url of urls) void fetch(url, { mode: "no-cors", cache: "no-store" }).catch(() => {});
}

function ensureAwake(base: string): Promise<void> {
  if (Date.now() - lastAnswer < ASLEEP_AFTER_MS) return Promise.resolve();
  waking ??= wake(base).finally(() => {
    waking = null;
  });
  return waking;
}

/**
 * fetch for /api requests that first makes sure the API is awake. A mutation is sent only to an
 * API that has just answered, so it is never sent twice. A GET or HEAD that still meets a
 * gateway error or a dropped connection (the API fell asleep since) waits for it once more and
 * is retried once.
 */
export async function awakeFetch(request: Request, nudgeUrls = NUDGE_URLS): Promise<Response> {
  nudge(nudgeUrls);
  await ensureAwake(request.url);
  const retry = IDEMPOTENT.has(request.method) ? request.clone() : null;
  try {
    const response = await fetch(request);
    if (!GATEWAY.has(response.status)) {
      lastAnswer = Date.now();
      return response;
    }
    if (!retry) return response;
  } catch (error) {
    if (!retry) throw error;
  }
  lastAnswer = 0;
  await ensureAwake(request.url);
  return fetch(retry);
}

/** Tests only: forget what the last test taught this module. */
export function resetWake() {
  lastAnswer = 0;
  lastNudge = null;
  waking = null;
  showNotice = false;
}
