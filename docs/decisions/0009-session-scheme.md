# 0009: Session scheme, API keys, stream tokens, rate limits

Status: accepted (2026-09-25). Amends PLAN.md §2 #3 (auth) and supersedes #20 (rate limiting).

## Context
In production the web app (Vercel) and the API are on different domains. Browsers increasingly block third-party cookies, so a cookie the API sets from its own domain can't be relied on from the web app's pages. Later, live run progress uses Server-Sent Events, and not every proxy streams responses without buffering. CLI and CI clients authenticate with project API keys, and never with a browser session.

The suggested design was:
- a short-lived JWT access token;
- an httpOnly refresh cookie;
- Next.js proxying `/api/*` to the API through rewrites;
- a stream-token fallback for SSE.

This ADR adopts it, with one change to where the access token lives (see 2).

## Decision

### 1. Same-origin through the proxy
Next.js rewrites `/api/:path*` to the API (implemented in E1). Every browser request is then same-origin: cookies are first-party, and no CORS is needed. The only exception is the SSE fallback in 5.

### 2. The access token is an httpOnly cookie, not a JS variable
This is the one deviation from the suggested design.
- **Token:** JWT (HS256, `JWT_SECRET` of at least 32 characters, checked at startup), 15 minutes, claims `sub`, `typ=access`, `iat`, `exp`.
- **Cookie:** `access_token`, with `HttpOnly; Secure; SameSite=Lax; Path=/`.

Keeping the access token in JS memory, as a Bearer header, only makes sense when cookies can't reach the API. The proxy removes that constraint, and then an in-memory token is strictly worse:
- any XSS can read and exfiltrate it, whereas an httpOnly cookie can only be *used* while the page is open;
- every page load needs a refresh round trip before the first API call.

The API never accepts a JWT in `Authorization`. That header carries API keys only, so browsers have exactly one credential path.

### 3. Refresh tokens are opaque, hashed, rotated, reuse-detected
- **Token:** 256 bits from `secrets.token_urlsafe`. Only its SHA-256 is stored, in `refresh_tokens (user_id, token_hash, expires_at, revoked_at)`. 30 days.
- **Cookie:** `refresh_token`, with `HttpOnly; Secure; SameSite=Strict`.
- **Rotation:** `POST /auth/refresh` revokes the presented token and issues a new pair.
- **Reuse detection:** presenting an already-revoked token means it was copied, so every live session of that user is revoked, and that revocation is committed even though the request fails with 401.
- **Logout:** `POST /auth/logout` revokes the current token and clears both cookies.
- **Known limit:** an access token that was already issued stays valid until it expires (at most 15 minutes).

### 4. CSRF
There are three layers:
- `SameSite` (Lax for access, Strict for refresh).
- For cookie-authenticated unsafe methods, `Origin` must equal `WEB_ORIGIN`; otherwise the request gets 403. Browsers always send `Origin` on non-GET fetches.
- FastAPI's strict content type: JSON bodies require `Content-Type: application/json`, so an HTML form can't reach a JSON endpoint.

PLAN §2 #3's "mutations require a JSON content type" rule still holds, via the third layer; the Origin check is added on top of it. API-key requests carry no ambient credential, so they skip the Origin check. Login CSRF (being logged into someone else's account) is left open for now: it's low impact while registration sits behind an allowlist.

### 5. SSE fallback: a stream token
If E4 shows the rewrite buffers `text/event-stream`, the browser connects to the API directly. This lands with the stream endpoint in B2.4; the token type exists and is tested now.
- **Minting:** `POST /runs/{id}/stream-token`, called through the proxy with the session cookie and the run-ownership check, returns a JWT with `typ=stream`, `run_id`, and a 60 s TTL.
- **Connecting:** the browser opens `new EventSource(API_PUBLIC_URL + "/runs/{id}/stream?token=…")`. `EventSource` can't set headers, and a third-party cookie wouldn't be sent, so a query token is the only portable option.
- **Checks:**
  - The API accepts `typ=stream` only on that route, and only for the matching `run_id`.
  - `decode_token` enforces `typ`, so a stream token is never an access token, and the other way round. Both directions are tested.
  - CORS is enabled on that single GET route only: `Access-Control-Allow-Origin: WEB_ORIGIN`, no credentials.
- **Not single-use:** `EventSource` reconnects on its own. The TTL and the run scope bound the damage; a reconnect after expiry fails, and the client mints a new token.
- **Leaks through query strings:** our access log redacts query parameters whose names look secret, and uvicorn's raw access log is disabled. Upstream proxy or CDN logs are covered only by the 60 s TTL.

### 6. API keys
- **Format:** `ap_` plus 32 random bytes, shown once at creation.
- **Storage:** the SHA-256 (a fast hash is fine at 256 bits of entropy; argon2 buys nothing) plus `last4` for display.
- **Revocation:** soft, via `revoked_at`. Revoked keys and unknown keys get the same 401.
- **Use:** `last_used_at` is updated on use; the lookup and the update are one `UPDATE … RETURNING`.
- **Scope:** a key is scoped to one project. `GET /projects` returns only that project, and other projects are 404. A key can never manage the account (create projects, or list, create or revoke keys), which is 403.
- **One dependency:** `get_principal` returns a `Principal` for a cookie session or for a key.

### 7. Ownership
Every lookup goes resource → project → user through `projects.owned_project`. Not-owned and nonexistent resources return the same 404, so ids can't be probed. `tests/idor.py` enforces this for every endpoint listed in `tests/test_idor.py::PROBES`.

### 8. Passwords
- argon2id with the library's current recommended parameters. The hash is rehashed on login when those parameters change, and hashing runs off the event loop.
- A login for an unknown email still pays for one verify (against a dummy hash), so response time doesn't reveal which emails exist.
- Length 12–128 at registration. Login applies no length policy.
- `SIGNUP_ALLOWED_EMAILS` gates registration (PLAN §2 #4). A duplicate email returns 409, which does enumerate registered emails; the allowlist and the IP rate limit bound that.

### 9. Rate limits
- **Interface:** `RateLimiter.acquire(bucket) -> retry_after | None`, a token bucket.
- **Backends:**
  - `MemoryTokenBucket` (default): per-process, marked `ponytail:`.
  - `RedisTokenBucket` (`RATE_LIMIT_BACKEND=redis`): one Lua script, atomic, using Redis' clock, so app-server clock skew is irrelevant. Tested against real Redis in CI.
- **Buckets:**
  - per API key: `RATE_LIMIT_PER_MINUTE`;
  - per client IP: one shared bucket for `/auth/register` and `/auth/login`, `AUTH_RATE_LIMIT_PER_MINUTE`.
- **Response:** 429 with `Retry-After` in whole seconds.
- **Client IP:** comes from uvicorn's proxy-header handling, which trusts `X-Forwarded-For` only from peers listed in `FORWARDED_ALLOW_IPS` (uvicorn reads this env var natively).
  - If it isn't set behind the proxy, every user shares the proxy's IP bucket.
  - If it's set to `*` while the API is publicly reachable, the header can be spoofed.
  - The deploy (F4) must allow only the proxy and keep the API unreachable except through it.

### 10. Errors and logs
- **Errors:** every non-2xx response is `{"error": {"code", "message", "request_id", "details?"}}`.
  - Validation errors return only `loc`, `msg` and `type`. FastAPI's `input` would echo passwords.
  - Unhandled errors become a generic 500 inside the request-ID context.
- **Request IDs:** a pure-ASGI middleware (so SSE isn't buffered) assigns or propagates `X-Request-ID` and writes one JSON access line per request.
- **Logs:** JSON, one object per line, via stdlib `logging`.
- **Redaction:** `RedactFilter` sits on the handler, so it also covers uvicorn, SQLAlchemy and tracebacks.
  - Any field whose name contains secret, token, key, password, authorization or cookie is replaced.
  - API keys, JWTs, `Bearer …` values and `name=value` pairs with such names are scrubbed from free text.

## Consequences
- One new table (`refresh_tokens`) and three columns on `api_keys` (migration 0002).
- The web app never touches tokens. E1 needs only the rewrite and `credentials: "same-origin"` fetches, and calls `/auth/refresh` when a request returns 401.
- The fallback adds one CORS-enabled route and one token type. Nothing else is reachable cross-origin.
- `tests/idor.py` is the contract for every future resource endpoint.
