// A cold API (ADR 0036). On the free tier the API sleeps after about 15 idle minutes and takes
// about a minute to wake. While it does, requests through /api hang or fail with a gateway
// error, which is not the user's problem to see as one: every API call waits here until
// /api/health answers, and the app shows a "waking the server" notice (WakingNotice) meanwhile.

const ASLEEP_AFTER_MS = 10 * 60_000; // re-check before calling an API quiet this long
const WAKE_BUDGET_MS = 150_000; // then give up; the request goes ahead and fails on its own
const PROBE_TIMEOUT_MS = 30_000; // a probe the platform holds this long is retried
const NOTICE_AFTER_MS = 1_500; // a warm API answers well within this: no notice flash
const GATEWAY = new Set([502, 503, 504]);
const IDEMPOTENT = new Set(["GET", "HEAD"]);

let lastAnswer = 0; // when the API last answered (any status but a gateway error)
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
export async function awakeFetch(request: Request): Promise<Response> {
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
  waking = null;
  showNotice = false;
}
