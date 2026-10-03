/** The API's public URL, for live run progress (ADR 0031); inlined at build time. Unset in a
 * production build without it: the run page then polls through /api. */
export const PUBLIC_API_URL: string | undefined =
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : undefined);
