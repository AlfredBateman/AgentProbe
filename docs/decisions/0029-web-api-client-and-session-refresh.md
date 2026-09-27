# 0029: Web API client, session refresh and route protection

Status: accepted (2026-09-28). Implements ADR 0009's web side (E1's plumbing).

## Context
ADR 0009 puts both tokens in httpOnly cookies behind the Next.js `/api` rewrite. The web app never sees a token, but it still decides when to call `POST /auth/refresh`. That call is dangerous to repeat: the refresh token rotates, and presenting an already-rotated one counts as theft, which revokes **every** session of that user. Two requests that both hit a 401, in one tab or in two tabs, must not both refresh.

## Decision

### 1. Typed client
- `scripts/export_openapi.py` writes the API's schema to `apps/web/src/lib/api/openapi.json`.
- `pnpm --filter web gen:api` runs `openapi-typescript` to produce `schema.d.ts`.
- Both files are committed, and two drift checks keep them current:
  - `apps/api/tests/test_openapi_schema.py` (offline) compares the JSON with the live app;
  - the web CI job regenerates the types and fails on a diff.
- At runtime the client is `openapi-fetch` (`createClient<paths>`), with base URL `/api`.

### 2. Single-flight refresh (`lib/api/session.ts`)
`createSessionFetch(onExpired)` wraps `fetch`. On a 401 it refreshes once and retries the request once, from a clone taken before sending, so request bodies survive.
- **In a tab**, concurrent 401s share one in-flight refresh promise.
- **Across tabs**, the refresh runs under a Web Lock (`navigator.locks`, name `agentprobe-session-refresh`). Inside the lock it first probes the new `GET /auth/me`. A 200 means another tab has already rotated the cookies, so no refresh is sent. Otherwise it sends exactly one `POST /auth/refresh`. Browsers without Web Locks get the in-tab guarantee only.
- A failed refresh calls `onExpired` once, which does a full page load of `/login?next=…`, so nothing from the dead session stays in memory.
- A retry that still fails is returned as it is, with no second refresh, so a failure can't loop.
- A 401 from `/auth/login`, `/auth/register`, `/auth/refresh` or `/auth/logout` passes through: there it means bad credentials, not an expired cookie. `/auth/me` is refreshed like any other request.
- The browser sets `Origin` on these same-origin POSTs, so the API's `Origin == WEB_ORIGIN` check passes through the rewrite unchanged. A cross-origin write through the proxy is still refused with 403 (checked manually through the running proxy).

### 3. `GET /auth/me`
A session-only endpoint (API keys get 403, like the other account routes) that returns `{id, email}`. It is the cross-tab probe and feeds the shell's account menu (user decision).

### 4. Route protection (`src/proxy.ts`, Next 16's renamed middleware)
- Public paths: `/`, `/login`, `/register`, `/shared/*` and `/dev/*`. `/api/*`, `_next/*` and files with an extension are also outside the matcher.
- Everything else needs an `access_token` or `refresh_token` cookie, or it redirects to `/login?next=<path>`.
- The proxy can't verify the JWT (it has no secret), so a cookie is only a hint. The API stays the authority, and a 401 that a refresh can't fix redirects anyway. The refresh cookie alone is enough, because an expired access cookie is refreshed on the first API call.

## Consequences
- Tests: 8 session tests. They cover 5 concurrent 401s with one refresh, two tabs with one refresh, the probe skipping the refresh, a failed refresh expiring once, no retry loop, credential endpoints passing through, `/auth/me` being refreshed, and a POST body surviving. Mutation-checked: removing the probe or the in-flight dedupe fails them.
- Verified end to end against a real API through the rewrite:
  - expiring the access cookie produced exactly one refresh;
  - sign-out cleared both cookies.
- **Known limit, for E1:** `refresh_token` is `SameSite=Strict`, so a navigation from another site (a link in an email or a PR comment) arrives without it. If the access cookie has also expired, the proxy sends the user to `/login` although their session is alive. `/login` should try a silent `POST /auth/refresh` before showing the form.
- The client is for client components. Server-side rendering against the API would have to forward cookies and can't set refreshed ones from a server component. That isn't needed yet.
