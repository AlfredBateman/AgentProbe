/** The API's public URL, for live run progress (ADR 0031); inlined at build time. Unset in a
 * production build without it: the run page then polls through /api. */
export const PUBLIC_API_URL: string | undefined =
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : undefined);

/**
 * Health URLs the browser pings directly to wake sleeping services (ADR 0036): the API's own,
 * plus NEXT_PUBLIC_WAKE_URLS (comma-separated; the public demo agents). The CSP allows their
 * origins.
 */
export const NUDGE_URLS: string[] = [
  ...(PUBLIC_API_URL ? [new URL("/health", PUBLIC_API_URL).href] : []),
  ...(process.env.NEXT_PUBLIC_WAKE_URLS ?? "")
    .split(",")
    .map((u) => u.trim())
    .filter(Boolean),
];
