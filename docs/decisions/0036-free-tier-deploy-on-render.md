# 0036: Production on free, no-card tiers: Render, Vercel Hobby and Neon

Status: accepted (2026-10-01). PLAN.md F4. Revised 2026-10-02 after the live checks
(§Checked on the live deploy): the client IP no longer comes from `X-Forwarded-For`, and the
demo agents' MCP route accepts Render's hostname. User constraint: no credit or debit card, so
production runs only on free tiers that don't ask for one. This ADR supersedes ADR 0035's
platform-specific parts: §Topology, §Deploy pipeline, §Client IPs, the demo agents' private
address, and its "Unverified" list. Everything else in ADR 0035 stands: `/ready`, open signup
and the per-user caps, the global live-LLM budget, the allowlist semantics (ADR 0012), and the
demo-agent label. The operator's guide is [docs/DEPLOY.md](../DEPLOY.md).

## Context
ADR 0035's host needed a card. The free, no-card options:
- **Vercel Hobby** for the web app (unchanged).
- **Render free web services** with the Docker runtime. As of 2026-10-01 (the user's brief):
  - a service sleeps after about 15 idle minutes and takes about a minute to wake;
  - 750 free instance hours a month, shared by the whole workspace;
  - no private-network traffic to free services;
  - 512 MB of memory per service.
- **Neon free** for Postgres, in its own production project (unchanged).

## Decision

### Topology
- **Web:** Vercel Hobby. `apps/web/vercel.json` and `PROXY_SECRET` are unchanged.
- **API:** a Render free web service built from `apps/api/Dockerfile`. Its Docker Command is
  `uvicorn agentprobe_api.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers`, so cold
  starts don't migrate. The health check is `/ready`. It uses `QUEUE_BACKEND=inline` and the
  in-memory rate limiter, with no Redis.
- **Demo agents:** a second, **public** Render free web service built from
  `demo-agents/Dockerfile`: `AGENT_MODE=mock`, no secrets, no database.
- **Services are created by hand** in the Render dashboard, not from a Blueprint. There's no
  `render.yaml`: Render reads one only through a Blueprint, so a committed copy would be
  documentation that drifts silently from the dashboard. docs/DEPLOY.md lists every setting.

### Deploy pipeline
`deploy.yml` keeps its trigger (CI succeeded on a push to `main`, exactly `head_sha`) and its
`DEPLOY_ENABLED` gate. It then:
1. runs `alembic upgrade head` against Neon from the runner;
2. POSTs the two Render deploy hooks (secrets `RENDER_DEMO_DEPLOY_HOOK` and
   `RENDER_API_DEPLOY_HOOK`) with `&ref=<sha>`, so Render builds the commit CI tested;
3. waits up to 30 minutes until the API's `/ready` reports that commit (`RENDER_GIT_COMMIT`,
   new in `/ready`'s body), which also proves the database answers;
4. builds and deploys the web app with the Vercel CLI, then checks `<web>/api/health`.

Auto-deploy is off on both Render services, so nothing ships before CI passes.

### Sleeping services, and no keep-alive
- **No pinger.** Each service awake all month needs about 744 hours, so two would need 1,488
  against the 750 the workspace gets. Both services sleep when idle and wake on demand.
- **Web (`lib/api/wake.ts`).**
  - Every `/api` call made after 10 quiet minutes waits for `/api/health` first. Probes back
    off 1, 2 and 4 s, then every 5 s. Each probe times out after 30 s, and the wait gives up
    after 150 s.
  - After 1.5 s the app shows "Waking the server, about 30 to 40 seconds" (`WakingNotice`, a live
    region), not an error.
  - A mutation is sent only to an API that has just answered, so it is never sent twice. A
    GET that meets a 502/503/504 or a dropped connection waits again and is retried once.
  - The public share page goes through the same gate.
- **Live progress (SSE).** The run page's stream hook (ADR 0031) already handles a dropped
  stream: it resyncs, reconnects with backoff (1 s up to 8 s), and polls after three failed
  connections. The stream opens only after the page's first API calls, so after any wake.
  Nothing new was needed.
- **API → demo agents (`wake.py`).** For hosts on `WAKE_TARGET_HOSTS`, a run's first attempt
  and a connection test are preceded by polling that host's `GET /health` for up to 120 s
  (one request may be held most of a minute while the host wakes). It is best effort: if the
  host never answers, the real call reports why. It goes through the SSRF guard;
  `guarded_client` was factored out of the HTTP adapter for this. It isn't on the Redis
  worker path, since production is inline.

### The demo agents are a public service
- Free services can't receive private traffic, so the demo agents are public. Every response
  carries `X-AgentProbe-Demo: Deliberately vulnerable demo with planted flaws. No real data:
  fake data only.`, and `GET /` returns the same notice. They are rule-based, hold no secrets
  and no data, and anyone may call them; each wake costs instance hours.
- **SSRF.** The demo host resolves to public addresses, so the guard admits it like any
  public host: resolved per connection, every address validated, the connect pinned to the
  validated address. Production runs `ALLOW_PRIVATE_TARGETS=0` with `PRIVATE_TARGET_ALLOWLIST`
  **empty**.
  - The brief asked for the host "on the SSRF allowlist as a public host" with no
    private-address exception. `PRIVATE_TARGET_ALLOWLIST` *is* a private-address exception
    (ADR 0012), so an entry there would create exactly what the brief rules out, and a public
    host needs no entry. There's no public-host allowlist, since users bring their own agents.
  - Tests:
    - `test_production_demo_host_is_public_with_no_private_exception`: production's policy,
      the agent's own `allow_private` on. A rebind to a private, loopback, ULA, metadata,
      link-local or unspecified address is refused, with one lookup per connection and the
      connect pinned.
    - `test_allowlisted_host_still_resolves_validates_and_pins`: the allowlist skips none of
      resolution, validation or pinning.

    Two planted bypasses, "allowlisted hosts skip resolution" and "reuse the first answer",
    fail 4 of 4 and 11 of 11 cases.
- The private-network hostname, its private-address exception, and the agent's
  `allow_private` in the smoke test are gone.

### Client IP (revised 2026-10-02 after the live check)
The request path is browser → Vercel's edge → `src/proxy.ts` → Vercel's rewrite → Render's
edge → the container.
- `src/proxy.ts` deletes any `x-agentprobe-client-ip` and `x-agentprobe-proxy-secret` the
  browser sent. With `PROXY_SECRET` set, it adds the secret and sets `x-agentprobe-client-ip`
  to Vercel's `x-real-ip` (Vercel's documented client IP, which `@vercel/functions`'
  `ipAddress()` also reads). Without `x-real-ip` it sends no client IP.
- The API trusts `x-agentprobe-client-ip` only when the secret matches (a constant-time
  compare; 32+ characters, checked at startup), and only if it parses as one IP address.
- Otherwise the API keys on the connecting address, which on Render is Render's proxy. That
  includes no secret, a wrong one, and a missing or malformed header.
- **`X-Forwarded-For` is never read.** The first design trusted its leftmost entry, on the
  strength of Vercel's documentation that its edge overwrites the header. The live check below
  showed a browser's own `X-Forwarded-For` sometimes arriving leftmost, so any visitor could
  pick their own rate-limit bucket.

So callers that skip the web app (the CLI, the GitHub Action, live-progress streams) share one
per-IP bucket. That's acceptable: they authenticate with API keys (per-key limits) or stream
tokens, and the per-IP limits guard only register and login, which go through the web proxy.

Removed: the earlier host's client-IP header and the API's own `FORWARDED_ALLOW_IPS` trust of
that host's proxy range. uvicorn runs with `--no-proxy-headers`.

**Failure mode:** if Vercel stopped sending `x-real-ip`, everyone through the web would share
one bucket (the proxy's address); nothing becomes spoofable, since the secret never reaches a
browser. Tests cover spoofed headers without the secret; wrong, prefixed and empty secrets; a
malformed or comma-separated value; a second header line; `X-Forwarded-For` with the secret;
`x-real-ip` sent straight to the API; and the proxy dropping a browser's own copies.

### The Origin check behind the proxies (first deploy, 2026-10-02)
The first deploy's registrations got 403 "Cross-origin request rejected".
- **The check.** `auth._check_origin` tests one condition: for any method except
  GET/HEAD/OPTIONS, the `Origin` header must equal `WEB_ORIGIN` exactly. It runs on
  register, login, refresh and logout, and on every cookie-authenticated request (an API
  key skips it). It ignores `Referer`, `Sec-Fetch-Site`, `Host`, `X-Forwarded-Host` and
  cookies.
- **The cause.** Render's `WEB_ORIGIN` was `https://agent-probe-umber.vercel.app/`, with
  the trailing slash the browser's address bar shows. A browser's `Origin` never has one.
  Reproduced with curl:
  - The browser's headers made no difference through the Vercel proxy, added one at a
    time: `Sec-Fetch-*`, `Referer`, `Content-Type`, a cookie. All got 403.
  - An `Origin` with the slash got 204, through the proxy and directly against Render. So
    `src/proxy.ts`, Vercel's rewrite and Render's edge pass `Origin` through unchanged.
- **Why curl looked fine.** curl with an empty `{}` body got a 422, but FastAPI validates
  the body before the endpoint runs, so the Origin check never ran. Probe with
  `POST /auth/logout`, which has no body.
- **Fix.** `Settings` reduces `WEB_ORIGIN` to `scheme://host[:port]`: a trailing slash is
  dropped, and scheme and host are lowercased. A path, query, fragment or credentials refuse
  to load. The comparison is still exact, against that one origin. The same value is the SSE
  route's `Access-Control-Allow-Origin`, which the slash had broken as well.
- **Diagnosis.** A rejection logs `cross-origin request rejected` (logger `agentprobe.auth`)
  with:
  - `reason`: `origin missing` or `origin != WEB_ORIGIN`;
  - `origin`, `web_origin`, `method` and `path`;
  - `sec_fetch_site`;
  - `referer_origin`: the Referer's scheme and host only, since its path or query can carry a
    share token.

  Cookies and the proxy secret are never logged.
- **Test.** `test_same_origin_browser_request_passes_through_vercel_and_render` sends the
  header set the container receives with `WEB_ORIGIN` configured with and without the slash.
  It fails on the old settings.

### Memory (512 MB per service)
Measured 2026-10-01 on the development machine: Windows, Python 3.12, the API's locked
dependencies without the `live` extra, production-like settings (inline queue, mock LLM,
memory limiter), against the Neon dev branch and local demo agents.

| State | Working set |
|---|---|
| Idle after startup | 130 MiB (108 MiB private) |
| Two concurrent 100-attempt mock runs, 16 polling clients, 6 SSE streams | 147 MiB peak |
| Idle after that load | 147 MiB |
| One registration | 194 MiB peak |

The registration peak is argon2. Each hash or verify allocates 64 MiB (argon2-cffi's RFC 9106
low-memory profile), and `asyncio.to_thread` runs up to min(32, CPUs + 4) at once. A burst of
a dozen logins would pass 512 MB.

**Fix:** at most `ARGON2_SLOTS = 2` argon2 operations run at a time (`auth._argon2`, a
semaphore per app). That bounds them to 128 MiB, which puts the worst case near 300 MiB.

Not changed:
- The production image has no `live` extra (`API_EXTRAS` empty), and LiteLLM isn't imported
  in mock mode.
- The `mcp` SDK costs 21 MiB and 0.6 s at import. It stays eager, well inside the bound.

### Checked on the live deploy (2026-10-02)
The first deploy left a list of assumptions only production could settle. Each was checked
against the live services; two were wrong and are fixed (`7f8ac29`).

**1. Client IP: was spoofable, fixed.** The probe was the hourly registration limit (5 per
IP). Re-registering an existing throwaway address answers 409 and still spends a token, so
nothing is created: 409 means "allowed", 429 means "limited".
- *Before the fix.*
  - Plain registrations from one machine through the web proxy were limited after five.
  - Then, with that machine's bucket empty, registrations carrying a made-up
    `X-Forwarded-For` still passed. Five sent with `198.51.100.250` filled a bucket of their
    own, and `198.51.100.250, 10.0.0.1` then got 429 from that same bucket.
  - So a browser's own `X-Forwarded-For` reached the API leftmost, though not every time: one
    such request did land in the real bucket. Any visitor could choose their own rate-limit
    bucket, contrary to Vercel's documentation.
  - Calls straight to Render were sound: one shared bucket (Render's proxy), limited after
    five whatever `X-Forwarded-For` said.
- *The fix:* §Client IP above.
- *After the fix* (fresh buckets, since the deploy restarted the API):
  - five plain registrations passed and the sixth got 429;
  - 13 more through the web proxy each got 429. Each carried a fresh made-up address in
    `X-Forwarded-For`, `X-Real-IP`, `X-Vercel-Forwarded-For` or `x-agentprobe-client-ip`, or
    in all four at once.
  - Sent straight to Render, the machine's own IP in `x-agentprobe-client-ip` with no secret,
    or with a wrong one, did not land in its exhausted bucket (409).
  - A GitHub runner, on another network, still registered through the web proxy at the same
    time (409).
  - Still to confirm (needs `PROXY_SECRET`, so only the operator can): that the key is
    exactly the browser's address. docs/DEPLOY.md step 10 has the commands.

**2. A deploy hook's `ref` builds that commit: yes.**
- With `main` at `a03afcc`, the API hook with `ref=4eca0bb` (code-identical, docs only)
  answered 200 with a deploy id. `/ready` reported `4eca0bb…` 63 s later.
- `ref=a03afcc` then restored it in 63 s.

**3. `RENDER_GIT_COMMIT` is set at runtime: yes.** `/ready` reports the full SHA, and it
followed every deploy: `a03afcc` → `4eca0bb` → `a03afcc` → `7f8ac29`.

**4. Wake times, and whether Render holds or answers 502: it holds.** After 15+ idle minutes,
every request to a sleeping service was held and answered 200 once it was up. No 502 or 503
was seen. The wake times are in §Cold starts below.

**5. Vercel's rewrite to a sleeping API: it waits.** `/api/health` through Vercel answered 200
after the API's full wake (32.6 s), with no gateway timeout.

**6. The demo agents' MCP route behind Render: was broken, fixed.**
- Every MCP request through Render answered 421 Misdirected Request. The MCP SDK's
  DNS-rebinding check, which `streamable_http_app()` turns on for its default host
  `127.0.0.1`, allowed only localhost `Host` values. Reproduced locally by sending the public
  `Host`.
- The fix: the allowlist is now the SDK's localhost defaults plus `RENDER_EXTERNAL_HOSTNAME`,
  which Render sets. Rebinding protection stays on, and any other host still gets 421
  (`demo-agents/tests/test_mcp_host.py`).
- After the fix, `suites/examples/mcp-safety.yaml` against the live route matches a local run:
  6 cases pass and the 3 planted flaws fail, with 0 errors.

**7. Render's free build allowance: 500 pipeline minutes a month (Hobby).**
- With no card on file, builds stop when the allowance is used up.
- An API deploy took 63 s from the hook to `/ready` (build included, with cached layers).
  Every push builds two images, so a few minutes per push, roughly 150 pushes a month.
- A change to `uv.lock` or a base image rebuilds more layers and costs more.
- The exact minutes are on Render's Billing page.

**Still unverified, and why:**
- **Build args** (`API_EXTRAS=live`). Render's Docker docs say it "automatically translates"
  service environment variables to build arguments. Exercising it means switching production
  to a different image (a dashboard change and a rebuild); production deliberately stays
  mock. To check: set `API_EXTRAS=live`, deploy, look for `litellm` in the build log, then
  remove it and deploy again.
- **An open SSE stream and Render's idle timer.** Render's free-tier docs count "HTTP requests
  and WebSocket messages" as activity and don't mention SSE, so assume a stream alone doesn't
  keep the API awake. Testing it needs a run lasting more than 15 minutes with only a stream
  open. If the instance does sleep mid-run, inline crash recovery resumes the run on the next
  start, and the stream reconnects or falls back to polling (ADR 0031).
- **Memory in the Linux image.** Render's per-service memory graph is visible only in its
  dashboard. The 512 MB bound in §Memory rests on the Windows measurement plus argon2's cap.
  To check: Render → `agentprobe-api` → Metrics → Memory, around a Deploy run's smoke test.

### Cold starts
Measured 2026-10-02 from a GitHub runner, which sent every request below at the same moment to
services that had been idle. The runner also ran `scripts/smoke_prod.py`, which passed both
times. A headless Chromium opened `/register`, created an account, and waited for the
dashboard; the throwaway accounts were deleted afterwards.

| | Sample 1: idle about 19 h | Sample 2: idle about 26 min |
|---|---|---|
| API `GET /health`, direct: held, then 200 | 32.5 s | 32.9 s |
| API through Vercel (`/api/health`): held, then 200 | 32.6 s | 32.9 s |
| Demo agents `GET /health`: held, then 200 | 22.7 s | 22.6 s |
| `smoke_prod.py`'s wake report (API `/ready`, demo `/health`) | 32 s, 22 s | 31 s, 21 s |
| Landing page `/` (static, Vercel only) | 0.8 s | 1.0 s |
| First visit: `/register` rendered | 1.4 s | 1.6 s |
| First visit: "Waking the server" notice shown | 3.2 s | 3.5 s |
| First visit: dashboard visible (after "Create account") | 36.9 s (35.5 s after submit) | 36.6 s (35.0 s after submit) |

So a free instance wakes in about 33 s (the API) and 23 s (the demo agents), not the brief's
"about a minute". The first page that needs the API shows about 37 s after a visitor opens
the site, with the notice up from about 3 s. The notice said "about a minute" until
2026-10-03; it now says "about 30 to 40 seconds", the measured wait.

## Consequences
- The first visitor after 15 idle minutes waits about 35 s (measured: §Cold starts), with the
  notice. A run against sleeping demo agents waits about 23 s more before its first attempt
  (up to 2 minutes, by `wake.py`'s budget).
- The in-memory rate limits reset whenever the API sleeps, that is after 15 idle minutes:
  only when there's no traffic to limit.
- Environment variables live in the Render dashboard, not in a reviewed file, so a change
  there isn't reviewed in a pull request. docs/DEPLOY.md is the reference to keep in step.
- Live Gemini stays an opt-in: `API_EXTRAS=live` on the API service (a build arg), plus
  `LLM_PROVIDER=litellm`, `RUN_LIVE=1` and `GEMINI_API_KEY`.
