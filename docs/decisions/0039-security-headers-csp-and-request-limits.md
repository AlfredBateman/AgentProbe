# 0039: Security headers, CSP and request limits

Date: 2026-10-03. Status: accepted. Part of F5 (hardening).

## Context

The review pass against SPEC.md §10 found that:
- neither the API nor the web app sent security headers;
- the API read every request body into memory with no size limit, including the anonymous
  `/auth/register`, on a 512 MB instance (ADR 0036);
- the two connection-test routes send a request to any public URL the caller chooses, with
  no limit;
- the GitHub Action installed `pip install agentprobe` by default, and that PyPI name
  belongs to an unrelated project.

CSRF (ADR 0009) and CORS were already right, but only CSRF had tests.

## Decision

- **API headers.** `RequestContextMiddleware` adds these to every response unless the route
  set its own:
  - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`
  - HSTS

  The HTML export keeps its own stricter CSP. FastAPI's `/docs` and `/redoc` get no CSP:
  they load Swagger UI from a CDN and hold no user data.
- **Web CSP, nonce-based.** `src/proxy.ts` mints a nonce per page request. Next puts it on its
  own scripts, which it reads from the request's CSP header. The policy:
  - `script-src 'self' 'nonce-…' 'strict-dynamic'` (plus `'unsafe-eval'` under `next dev` only);
  - `style-src 'self' 'unsafe-inline'`: React renders style attributes, which a nonce can't
    cover;
  - `connect-src 'self'` plus the API's public origin, for live progress (ADR 0031);
  - `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`, `form-action 'self'`.

  The root layout is `force-dynamic`: a page prerendered at build time would carry no nonce,
  so its scripts would be blocked. Static headers (nosniff, `X-Frame-Options`,
  `Referrer-Policy: same-origin` because a share link's token is in its path,
  `Permissions-Policy`, HSTS) come from `next.config.ts` for everything except `/api/*`.
- **CORS** stays without middleware. The browser reaches the API through the same-origin
  `/api` proxy. The only cross-origin read is the token-authenticated SSE stream, allowed for
  `WEB_ORIGIN` (ADR 0031). Preflights get 405. Now tested.
- **Body cap: 10 MiB** (`MAX_BODY_BYTES`). A larger declared `Content-Length` gets a 413
  before the body is read. A chunked body is cut off as it passes the cap, through FastAPI's
  `HTTPException`, because anything else raised while FastAPI reads a body becomes a 400. One
  global cap (`ponytail:`): per-route caps if `/ci/report` uploads ever outgrow it.
- **Connection tests are limited per account**: `CONNECTION_TEST_RATE_LIMIT_PER_MINUTE`
  (default 20), one bucket shared by the saved-agent and draft routes. It uses the same token
  buckets as the other limits.
- **The Action installs the CLI from its own source** (`$GITHUB_ACTION_PATH/../packages/*`)
  when `cli-package` is empty, which is the new default. A workflow pinning the action at a
  ref gets the CLI from that ref. The docs install by git URL.
- **Secret scanning.** CI's `audit` job runs gitleaks 8.30.1, checksum-pinned, over every
  commit on every ref. `.gitleaksignore` lists the three known public dev values by
  fingerprint.

## Consequences

- Every web page renders per request: on Vercel Hobby that's one function invocation per page
  view, instead of serving prerendered static HTML.
- A future third-party script or style host must be added to the CSP in `src/proxy.ts`. The
  e2e visual-snapshot spec fails on any CSP violation.
- Before this, the Action's default could install a stranger's package in a user's CI. Any
  workflow that set `cli-package: agentprobe` explicitly still does, and the input's
  description warns against it.
- Publishing the CLI to PyPI needs a free name (a user decision). Until then, the git URL is
  the install path.
