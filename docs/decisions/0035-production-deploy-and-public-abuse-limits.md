# 0035: Production deploy, client-IP trust, and public-abuse limits

Status: accepted (2026-09-29). PLAN.md F4. The user chose the proxy approach and open signup
from a researched comparison (2026-09-29).

**Partly superseded by [ADR 0036](0036-free-tier-deploy-on-render.md) (2026-10-01):** the
first hosting choice needed a credit card, which the user doesn't have. ADR 0036 replaces this
ADR's hosting topology, deploy pipeline, client-IP trust, the demo agents' private address and
the "unverified" list. Those sections below now only point there. Readiness, open signup and
the caps, the global live-LLM budget, the allowlist semantics and the demo-agent label stand
as written. The operator's guide is [docs/DEPLOY.md](../DEPLOY.md).

## Context
SPEC.md targets Vercel, a container host, Neon and Upstash. The free-tier terms as of
2026-09-29:
- **Render:** free web services sleep after 15 idle minutes and take about a minute to wake;
  workers aren't free ($7/month each).
- **Upstash:** 500K commands a month. Our taskiq worker's idle XREADGROUP polling (2
  processes, one call per 2 s each) is about 2.6M a month, so the quota runs out in about six
  days, and then Redis answers `ERR max requests limit exceeded`.

So production uses the inline queue and no Redis, whatever the host.

## Decision

### Topology
Superseded by ADR 0036 §Topology. Still true: the API runs `QUEUE_BACKEND=inline` with the
in-memory rate limiter; Postgres is Neon, in its own production project, so it doesn't share
the dev and test project's compute quota; there's no Redis in production, and CI's `docker`
job keeps proving the Redis path (ADR 0033); the platform runs uvicorn without the image's
migrate-then-serve command, so cold starts don't migrate.

### Deploy pipeline
Superseded by ADR 0036 §Deploy pipeline. Still true: `deploy.yml` runs on `workflow_run` after
CI succeeds on a push to `main`, checks out exactly `head_sha`, migrates first, deploys the web
app with the Vercel CLI (`apps/web/vercel.json` turns Vercel's own Git deploys off), and is
disarmed until the repository variable `DEPLOY_ENABLED` is `true`.

### Readiness
`GET /ready` runs `SELECT 1`, returning 200 or 503. It's the platform's health check (so a
deploy isn't healthy until the database answers) and deploy.yml's post-deploy gate. `GET
/health` stays a pure liveness check.

### Client IPs
Superseded by ADR 0036 §Client IP. Still true: Vercel's egress IPs aren't published below
Enterprise, so the API can't recognize the web proxy by address; `src/proxy.ts` forwards
`/api/*` itself (replacing the `next.config.ts` rewrite) and proves itself with
`x-agentprobe-proxy-secret` (`PROXY_SECRET`, 32+ characters, a constant-time compare); the API
stays public, because live progress streams (ADR 0031), the CLI and the GitHub Action (API
keys) call it directly.

`API_INTERNAL_URL` is now read per request, not baked in at build time. That fixes ADR 0033's
rebuild-to-repoint limitation for the web image.

### Open signup, and caps for a public demo
- `SIGNUP_OPEN=1` lets anyone register. The allowlist stays for invite-only deploys.
- Register and login now also need `Origin == WEB_ORIGIN`. ADR 0009 left login CSRF open only
  "while registration sits behind an allowlist".
- **Rate limits:** `REGISTER_RATE_LIMIT_PER_HOUR` per IP, on top of the per-minute auth limit.
  The token buckets gained a window argument for this.
- **Caps**, all `None` (unlimited) by default for local and self-hosted use, with production
  values in docs/DEPLOY.md:
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
- `LLM_PROVIDER=litellm` and `RUN_LIVE=1` on the API;
- `GEMINI_API_KEY`.

A live run builds at most two budget-guarded clients (judges, then clustering), each capped at
`LLM_BUDGET_USD_PER_RUN`. So the guard reserves twice that per non-mock run created in the last
24 hours. It refuses a new live run, or a non-mock CI report (whose clustering calls the LLM),
when the reservations would pass `LLM_GLOBAL_USD_PER_DAY`. Counting runs instead of summing
`judge_cost_usd` keeps the bound exact without trusting costs that `/ci/report` payloads claim.
The per-host daily cap in a local file (ADR 0011) stays, but a container's disk is ephemeral,
so this guard is the real one.

### Private targets: an allowlist is the whole server policy
`TargetPolicy.permits_private` changed (ADR 0012 amended):
- when `PRIVATE_TARGET_ALLOWLIST` is set, a private host is allowed only if it's on the list,
  whatever `ALLOW_PRIVATE_TARGETS` says;
- with no allowlist, the flag decides, as before.

The agent's own `allow_private` is still required. Production's use of this (the demo agents
on a private address) is superseded by ADR 0036: the demo agents are public, and production
allows no private targets at all.

### Demo agents labelled
Every demo-agent response carries an `X-AgentProbe-Demo` header saying they're deliberately
vulnerable with fake data only, and `GET /` returns the same (wording updated in ADR 0036).
The service has `AGENT_MODE=mock` and no secrets.

## Consequences
- Cold starts, where the limiter resets, and what can't be verified before the first deploy:
  superseded by ADR 0036.
- **Caps are per account:** they don't stop someone with many accounts. `MAX_SIGNUPS_PER_DAY`
  and the global LLM budget are the backstops for storage and money.
- **A resumed run can overspend:** it builds fresh LLM clients, so it can exceed its
  reservation.
