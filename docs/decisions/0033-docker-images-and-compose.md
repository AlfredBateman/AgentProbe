# 0033: Docker images, the compose stack, and its CI smoke test

Status: accepted (2026-09-29). Completes PLAN.md F3.

Amended 2026-09-29 by [ADR 0035](0035-production-deploy-on-fly-and-vercel.md): the web image reads `API_INTERNAL_URL` at runtime (compose sets it on the `web` service), so it's no longer a build arg; the API image carries `config/` and builds with LiteLLM when given `--build-arg API_EXTRAS=live` (CI builds that variant too).

## Context
F3 ships Dockerfiles and a `docker-compose.yml` so that `docker compose up` runs the whole stack
with no API keys. The developer can't run Docker locally (PLAN.md §2 #17), so CI is the only
place any of it is built or run. Everything here has to be right from reading, then proven by
CI's `docker` job.

## Decision

### Three images, all multi-stage, pinned and non-root
- `apps/api/Dockerfile` is one image for the API and the Redis worker. The default command
  migrates, then serves: `alembic upgrade head && exec uvicorn …`. The compose `worker`
  service reuses the image by tag and overrides the command with
  `taskiq worker agentprobe_api.worker:broker`. The venv is built non-editable, so the final
  stage holds only `.venv`, `alembic.ini` and `migrations/`.
- The API's `/health` check is in the compose `api` service, not in the Dockerfile. The worker
  runs the same image and has no HTTP port. `healthcheck: disable: true` on the worker would
  make `docker compose up --wait` fail ("has no healthcheck configured", seen in CI), because
  Compose falls back to "running" only when the image defines no healthcheck at all. So the
  worker has none. The smoke test's run proves it works. A liveness check for it (its Redis
  consumer's idle time, which a polling worker resets every 2 s) is for when a deploy platform
  needs one (F4).
- `demo-agents/Dockerfile` is an editable install that keeps the source tree, because
  `routes_support.py` finds `prompts/` relative to its own file. It binds 0.0.0.0 inside the
  container only; `python -m agentprobe_demo_agents` still binds 127.0.0.1.
- `apps/web/Dockerfile` is Next.js standalone output on `node:22-alpine`. Standalone is
  switched on by `NEXT_OUTPUT=standalone`, which only this Dockerfile sets. It stays off for
  `next build` elsewhere, because standalone copies `node_modules` as symlinks and Windows
  restricts those.
- The base images are pinned by version tag and digest: Python 3.12.14 slim-trixie, Node
  22.23.3 Alpine, uv 0.12.18 (the CI version), pgvector 0.8.6-pg18 (the CI and Neon version)
  and Redis 8.8.3 Alpine. The images run as uid 10001 (`app`) or the Node image's `node`
  user. Each Dockerfile has its own allowlist `Dockerfile.dockerignore`, so the build context
  never contains `.env`, `.venv` or `node_modules`.
- The images don't include the `live` extra (LiteLLM and its large tree). The server runs
  with mock judges by default (`RunIn.mock`), and adding live judging is deploy work (F4).

### Build-time web settings
`API_INTERNAL_URL` (the `/api` rewrite target) and `NEXT_PUBLIC_API_URL` (the browser's SSE
origin, ADR 0031) are fixed when `next build` runs, not when the server starts. So they're build
args, defaulting to `http://api:8000` and `http://localhost:8000`.

### The compose stack is for local use only
- Its `JWT_SECRET`, `ENCRYPTION_KEY` and Postgres password are committed and so public. The
  file says never to deploy it.
- Published ports bind to 127.0.0.1 (web 3000, API 8000). Postgres, Redis and the
  deliberately vulnerable demo agents publish nothing.
- There's no `${VAR}` interpolation at all. Compose reads a `.env` in the project directory
  for interpolation, and this repo's `.env` holds the developer's Neon URLs and real keys.
- The defaults are the Redis queue (`QUEUE_BACKEND=redis`), the Redis rate limiter and the
  mock LLM. `ALLOW_PRIVATE_TARGETS=1` is limited by `PRIVATE_TARGET_ALLOWLIST=demo-agents`
  (ADR 0012).
- `DATABASE_URL` carries `sslmode=disable`, because `db.py` adds `sslmode=require` for any host
  but localhost.
- Startup order uses health conditions. `api` waits for healthy `db` and `redis`; `worker`
  and `web` wait for a healthy `api`, which means migrations have run. The Postgres check
  uses TCP (`pg_isready -h 127.0.0.1`), because on first start the entrypoint's temporary
  init server listens only on the unix socket.
- Only `demo@example.com` (for people) and `smoke@example.com` (for the smoke test) may sign
  up.

### The CI job is the README quick start
The `docker` job runs `docker compose build`, `docker compose up -d --wait`,
`python3 scripts/compose_smoke.py` and `docker compose down -v`: the README's commands in the
same order. On failure it dumps `docker compose ps -a` and the logs, and teardown always runs.
The smoke script is stdlib-only, so any Python 3.9+ runs it without the repo's venv:
- It checks `/health` on the API and `/login` on the web app.
- It goes through the web app's `/api` rewrite to register (or log in on a rerun), create a
  project, an HTTP agent at `http://demo-agents:9000/support/v1/chat` and the smoke suite,
  then start a run.
- It polls until the run finishes, and asserts `completed` with a pass rate in [0, 1].

Going through the rewrite also proves that the web container reaches the API. The run proves
that migrations, the Redis queue, a real `taskiq worker` process, the SSRF opt-in and the demo
agents all work together. It's the first time CI runs the worker as its own process; the
`redis` pytest marker only runs jobs in-process.

## Consequences
- A change to a Dockerfile, the compose file or the smoke script is only verified by CI's
  `docker` job.
- The images can't make live LLM calls until F4 adds the `live` extra (a build arg, or a
  separate target).
- Rebuilding the web image is needed to point it at a different API. The runtime environment
  can't change the rewrite target.
