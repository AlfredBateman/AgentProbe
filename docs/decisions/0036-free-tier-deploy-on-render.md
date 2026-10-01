# 0036: Production on free, no-card tiers: Render, Vercel Hobby and Neon

Status: accepted (2026-10-01). PLAN.md F4. User constraint: no credit or debit card, so
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
  - After 1.5 s the app shows "Waking the server, about a minute" (`WakingNotice`, a live
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

### Client IP
The request path is browser → Vercel's edge → `src/proxy.ts` → Vercel's rewrite → Render's
edge → the container.
- Vercel's edge overwrites `X-Forwarded-For` with the real client.
- `src/proxy.ts` replaces it with exactly that address and adds `x-agentprobe-proxy-secret`.
- The hops after it append, so **the leftmost entry is the browser**. The API trusts it only
  when the secret matches (a constant-time compare; 32+ characters, checked at startup).
- Otherwise the API keys on the connecting address, which on Render is Render's proxy. That
  includes no secret, a wrong one, and a malformed or missing entry.

So callers that skip the web app (the CLI, the GitHub Action, live-progress streams) share one
per-IP bucket. That's acceptable: they authenticate with API keys (per-key limits) or stream
tokens, and the per-IP limits guard only register and login, which go through the web proxy.

Removed: `CLIENT_IP_HEADER` (the earlier host's client-IP header), the API's own
`FORWARDED_ALLOW_IPS` trust of that host's proxy range, and `x-agentprobe-client-ip`. uvicorn
runs with `--no-proxy-headers`.

**Failure mode:** if a hop replaced `X-Forwarded-For` instead of appending, the leftmost entry
would be Vercel's or Render's address. Everyone would then share one bucket, but nothing
becomes spoofable: the secret never reaches a browser. Tests cover spoofed headers without the
secret, wrong, prefixed and empty secrets, a malformed entry, a second header line, and the
retired header.

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

### Unverified until the first live deploy
- That Vercel's external rewrite keeps the middleware's `X-Forwarded-For` (or puts the client
  first itself), and that Render's edge appends rather than replaces it. Check: six
  registrations from one network should give a 429 on the sixth
  (`REGISTER_RATE_LIMIT_PER_HOUR=5`), while one from another network still succeeds.
- That a deploy hook's `ref` parameter builds that commit. If it doesn't, the `/ready` commit
  wait fails loudly.
- That `RENDER_GIT_COMMIT` is set at runtime for a Docker service built from the repository.
  If it isn't, the same wait times out.
- That Render passes service environment variables to `docker build` as build args (the
  `API_EXTRAS=live` opt-in).
- Wake and cold-start times on a free instance, and whether Render holds a request while a
  service wakes or answers 502. The web and the API handle both.
- Whether Vercel's rewrite to a sleeping API times out first. The web's probes retry through
  it either way.
- Whether an open SSE stream counts as activity for Render's idle timer. A run whose instance
  sleeps or restarts mid-run is resumed by inline crash recovery on the next start.
- Render's free build allowance. Every push to `main` builds both images.
- Memory in the Linux image (measured on Windows).
- The demo agents' MCP route (`/mcp`) behind Render's proxy.

## Consequences
- The first visitor after 15 idle minutes waits about a minute, with the notice. A run against
  sleeping demo agents waits up to 2 more minutes before its first attempt.
- The in-memory rate limits reset whenever the API sleeps, that is after 15 idle minutes:
  only when there's no traffic to limit.
- Environment variables live in the Render dashboard, not in a reviewed file, so a change
  there isn't reviewed in a pull request. docs/DEPLOY.md is the reference to keep in step.
- Live Gemini stays an opt-in: `API_EXTRAS=live` on the API service (a build arg), plus
  `LLM_PROVIDER=litellm`, `RUN_LIVE=1` and `GEMINI_API_KEY`.
