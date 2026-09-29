# 0035: Production deploy on Fly.io and Vercel, client-IP trust, and public-abuse limits

Status: accepted (2026-09-29). PLAN.md F4. The user chose the hosting option, the proxy approach
and open signup from a researched comparison (2026-09-29). The operator's guide is
[docs/DEPLOY.md](../DEPLOY.md).

## Context
SPEC.md targets Vercel, Render or Fly.io, Neon and Upstash. The free-tier terms as of
2026-09-29:
- **Render:** free web services sleep after 15 idle minutes and take about a minute to wake;
  workers aren't free ($7/month each).
- **Fly.io:** no free tier (a 2-hour trial). A stopped machine bills only its disk, and a
  worker, having no HTTP service, can never stop.
- **Upstash:** 500K commands a month. Our taskiq worker's idle XREADGROUP polling (2
  processes, one call per 2 s each) is about 2.6M a month, so the quota runs out in about six
  days, and then Redis answers `ERR max requests limit exceeded`.

The user chose "Fly, scale to zero": about $1–5/month, the inline queue, no Redis in
production.

## Decision

### Topology
- **Web:** Vercel Hobby.
- **API:** one Fly machine (`shared-cpu-1x`, 512 MB, region `sin`, next to Neon's
  `ap-southeast-1`) with `QUEUE_BACKEND=inline` and the in-memory rate limiter. It stops when
  idle and starts on the next request. Inline crash recovery resumes a run a stop interrupted.
- **Demo agents:** their own Fly app with no public IP, reachable as `<app>.flycast` over
  Fly's private network.
- **Postgres:** Neon, in its own production project, so it doesn't share the dev and test
  project's 100 CU-hour quota.
- **Redis:** none in production. CI's `docker` job keeps proving the Redis path (ADR 0033).
- **Commands:** Fly runs uvicorn without the image's migrate-then-serve command, so cold starts
  don't migrate.

### Deploy pipeline
`deploy.yml` runs on `workflow_run` after CI succeeds on a push to `main`, and checks out
exactly `head_sha`. It then:
1. runs `alembic upgrade head` against the production database from the runner;
2. builds both images with the Dockerfiles and contexts CI's `docker` job proves, and pushes
   them to Fly's registry tagged with the commit;
3. deploys the demo agents (`--no-public-ips`), then the API, and checks `/ready`;
4. builds and deploys the web app with the Vercel CLI (`apps/web/vercel.json` turns Vercel's
   own Git deploys off, so nothing ships before CI passes);
5. checks `https://<web>/api/health`.

The job is disarmed until the repository variable `DEPLOY_ENABLED` is `true`.

### Readiness
`GET /ready` runs `SELECT 1`, returning 200 or 503. It's Fly's health check (so a deploy
isn't healthy until the database answers) and deploy.yml's post-deploy gate. `GET /health`
stays a pure liveness check.

### Client IPs: two trusted headers, each with its own proof
Per-IP limits have to see the browser, and neither proxy can be trusted by address:
- **Vercel.** Its egress IPs aren't published below Enterprise. It does overwrite
  `X-Forwarded-For` with the real client. `src/proxy.ts` now forwards `/api/*` itself
  (replacing the `next.config.ts` rewrite) and adds `x-agentprobe-proxy-secret` and
  `x-agentprobe-client-ip`, dropping any copies the browser sent. The API uses that IP only
  when the secret matches (constant-time compare, `PROXY_SECRET`, 32+ characters).
- **Fly.** Fly appends to `X-Forwarded-For`, and its rightmost entry is Fly's own address, so
  uvicorn's "rightmost untrusted" rule would key every direct caller on Fly. The API instead
  trusts `CLIENT_IP_HEADER=Fly-Client-IP`, which Fly's proxy sets itself, only from a
  `FORWARDED_ALLOW_IPS` peer (`172.16.0.0/12`, the range its proxy connects from). uvicorn
  runs with `--no-proxy-headers`, so that peer is the real TCP peer.
- **The API stays public.** Live progress streams (ADR 0031) and the CLI and GitHub Action
  (API keys) call it directly. "Reachable only through the proxy" holds at the network level:
  the machine binds IPv4 only, so only Fly's proxy reaches it, and IP trust flows only
  through the two headers above.

`API_INTERNAL_URL` is now read per request, not baked in at build time. That fixes ADR 0033's
rebuild-to-repoint limitation for the web image.

### Open signup, and caps for a public demo
- `SIGNUP_OPEN=1` lets anyone register. The allowlist stays for invite-only deploys.
- Register and login now also need `Origin == WEB_ORIGIN`. ADR 0009 left login CSRF open only
  "while registration sits behind an allowlist".
- **Rate limits:** `REGISTER_RATE_LIMIT_PER_HOUR` per IP, on top of the per-minute auth limit.
  The token buckets gained a window argument for this.
- **Caps**, all `None` (unlimited) by default for local and self-hosted use, with production
  values in `fly.api.toml`:
  - `MAX_SIGNUPS_PER_DAY` (global);
  - `MAX_PROJECTS_PER_USER`;
  - `MAX_AGENTS_PER_USER`;
  - `MAX_CASES_PER_SUITE` (on suite create and update);
  - `MAX_RUNS_PER_USER_PER_DAY` (server runs and CI reports, rolling 24 h).
- The caps count, then insert, so concurrent requests can overshoot by one (a `ponytail:`
  note in `limits.py`).

### A global live-LLM budget from a worst case, not from metered spend
Mock judges are the production default. Live Gemini needs three things:
- the `live` extra, which the image installs only with `API_EXTRAS=live`; CI builds that
  variant;
- `LLM_PROVIDER=litellm` and `RUN_LIVE=1` in `fly.api.toml`;
- `GEMINI_API_KEY`.

A live run builds at most two budget-guarded clients (judges, then clustering), each capped at
`LLM_BUDGET_USD_PER_RUN`. So the guard reserves twice that per non-mock run created in the last
24 hours. It refuses a new live run, or a non-mock CI report (whose clustering calls the LLM),
when the reservations would pass `LLM_GLOBAL_USD_PER_DAY`. Counting runs instead of summing
`judge_cost_usd` keeps the bound exact without trusting costs that `/ci/report` payloads claim.
The per-host daily cap in a local file (ADR 0011) stays, but Fly's disk is ephemeral, so this
guard is the real one.

### Private targets: an allowlist is the whole server policy
`TargetPolicy.permits_private` changed (ADR 0012 amended):
- when `PRIVATE_TARGET_ALLOWLIST` is set, a private host is allowed only if it's on the list,
  whatever `ALLOW_PRIVATE_TARGETS` says;
- with no allowlist, the flag decides, as before.

So production runs with `ALLOW_PRIVATE_TARGETS=0` and `PRIVATE_TARGET_ALLOWLIST=<demo
app>.flycast`. The agent's own `allow_private` is still required.

### Demo agents labelled
Every demo-agent response carries
`X-AgentProbe-Demo: Deliberately vulnerable test targets with planted flaws. Fake data only.`,
and `GET /` returns the same. The Fly app has `AGENT_MODE=mock` and no secrets.

## Consequences
- **Cold starts:** the first request after the API has been idle waits for a machine start,
  and the first run after the demo agents have been idle waits for theirs. The HTTP adapter's
  30 s timeout covers a start measured in seconds, which is still to be measured on the
  deploy.
- **Where the limiter resets:** the rate limits live in one process's memory. They reset only
  when the machine stops, which happens only when there's no traffic to limit.
- **Unverified until a real deploy:**
  - Vercel forwarding the middleware's request headers on an external rewrite;
  - Fly's proxy source range (172.16.0.0/12, from Fly's community reports rather than its
    docs);
  - whether an open SSE stream keeps a Fly machine running.

  docs/DEPLOY.md step 9 checks the flow end to end. If the source range is wrong, direct
  callers all key on Fly's proxy address; nothing becomes spoofable.
- **Caps are per account:** they don't stop someone with many accounts. `MAX_SIGNUPS_PER_DAY`
  and the global LLM budget are the backstops for storage and money.
- **A resumed run can overspend:** it builds fresh LLM clients, so it can exceed its
  reservation.
- **The deployed MCP route is untested:** the demo agents' MCP route (`/mcp`) hasn't been
  checked behind a `.flycast` Host header.
