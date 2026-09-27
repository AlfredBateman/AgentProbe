import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { createSessionFetch } from "./session";

function toLogin() {
  const next = window.location.pathname + window.location.search;
  // A full load, not router.push: nothing from the expired session survives in memory.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

/**
 * The typed API client for client components. Requests go to /api, which Next rewrites to the
 * API, so cookies are first-party (ADR 0009). Types come from the API's OpenAPI schema:
 * `uv run python scripts/export_openapi.py && pnpm --filter web gen:api`.
 */
export const api = createClient<paths>({ baseUrl: "/api", fetch: createSessionFetch(toLogin) });
