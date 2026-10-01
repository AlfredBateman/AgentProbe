# Deploying AgentProbe

The production demo runs on free tiers that don't need a card ([ADR 0036](decisions/0036-free-tier-deploy-on-render.md); the abuse limits are from [ADR 0035](decisions/0035-production-deploy-and-public-abuse-limits.md)):

| Service | Where | Notes |
|---|---|---|
| Web (Next.js) | Vercel, Hobby | Forwards `/api/*` to the API (`src/proxy.ts`) with the proxy secret, and sets `X-Forwarded-For` to the browser's IP. |
| API | Render free web service, Docker runtime | `QUEUE_BACKEND=inline`, no Redis. Sleeps after about 15 idle minutes; wakes on the next request in about a minute. |
| Demo agents | Render free web service, Docker runtime, **public** | Deliberately vulnerable, fake data only, labelled on every response. Sleeps like the API; the API wakes it before a run. |
| Postgres | Neon Free, its own project, AWS `ap-southeast-1` | Separate from the dev and test branches' project, so it has its own compute quota. |

There's no Redis in production. CI's `docker` job proves the Redis queue path instead (ADR 0033).

`.github/workflows/deploy.yml` deploys after CI passes on `main`, on the commit CI tested:
1. it runs the migrations;
2. it calls both Render deploy hooks for that commit;
3. it waits until the API's `/ready` reports that commit;
4. it deploys the web app;
5. it checks that `https://<web>/api/health` reaches the API.

It does nothing until the repository variable `DEPLOY_ENABLED` is `true`. Render's own auto-deploy stays off.

## Free-tier behaviour
- **Sleeping.** Free services sleep after about 15 idle minutes and take about a minute to wake. The free plan's 750 instance hours a month are shared by the workspace, and two services awake all month would need about 1,488. So there's **no keep-alive pinger**: don't add one, or an uptime monitor that does the same.
- **The web app** waits for a sleeping API before its first request after 10 quiet minutes (`lib/api/wake.ts`). It shows "Waking the server, about a minute" if that takes more than 1.5 s, gives up after 150 s, and never sends a mutation twice. Live run progress already reconnects with backoff and falls back to polling (ADR 0031).
- **The demo agents** are woken by the API (`WAKE_TARGET_HOSTS`). Before a run's first attempt, and before a connection test, the API polls their `/health` for up to 2 minutes.
- **Memory:** 512 MB per service. The API measured about 130 MiB idle and 147 MiB under two concurrent runs. argon2 is limited to two hashes at a time (64 MiB each). Details are in ADR 0036.

## Health and readiness
| Endpoint | Meaning | Used by |
|---|---|---|
| API `GET /health` | The process answers. Touches nothing else. | The web app's wake-up probe, the compose healthcheck |
| API `GET /ready` | The database answers too (`SELECT 1`), with the deployed `commit`; 503 otherwise. | Render's health check, deploy.yml's wait for the new commit |
| Demo agents `GET /health` | The process answers. | Render's health check, the API's wake-up, the compose healthcheck |

## Render services
Both are created by hand in the Render dashboard (New > Web Service), from this GitHub repository. Neither uses a Blueprint, and there's no `render.yaml`: Render only reads one through a Blueprint, so this table is the reference. Keep it in step with the dashboard.

| Setting | API | Demo agents |
|---|---|---|
| Name | `agentprobe-api` | `agentprobe-demo-agents` |
| Language / runtime | Docker | Docker |
| Branch | `main` | `main` |
| Region | Singapore (next to Neon's `ap-southeast-1`) | Singapore |
| Root Directory | empty (the repository root; both Dockerfiles build from it) | empty |
| Dockerfile Path | `./apps/api/Dockerfile` | `./demo-agents/Dockerfile` |
| Docker Build Context Directory | `.` | `.` |
| Docker Command | `uvicorn agentprobe_api.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers` (no migrations at start: deploy.yml migrates first) | empty (the image's own command) |
| Instance type | Free | Free |
| Health Check Path | `/ready` | `/health` |
| Auto-Deploy | **Off** (deploy.yml calls the deploy hook after CI) | **Off** |

Render names the public URL after the service (`https://<name>.onrender.com`) and adds a suffix if the name is taken. Use the URL Render actually shows.

### API environment
| Variable | Value | Why |
|---|---|---|
| `PORT` | `8000` | The port uvicorn listens on; Render routes to it. |
| `DATABASE_URL` | The Neon production connection string: the **direct** host (no `-pooler`), with `sslmode=require&channel_binding=require`. Paste Neon's string as-is. | |
| `JWT_SECRET` | 32+ random characters | The API refuses to start with less. |
| `ENCRYPTION_KEY` | A Fernet key | Encrypts stored agent auth headers. Losing it makes them unreadable, and rotating it needs a re-encryption (ADR 0003). |
| `PROXY_SECRET` | 32+ random characters, **the same value** as the Vercel project's | Only requests carrying it have `X-Forwarded-For` trusted. |
| `WEB_ORIGIN` | The Vercel production URL, e.g. `https://agentprobe.vercel.app`, no trailing slash | The Origin check and the SSE route's CORS. |
| `PUBLIC_WEB_URL` | Same as `WEB_ORIGIN` | Links in exports and PR comments. |
| `WAKE_TARGET_HOSTS` | The demo agents' hostname, e.g. `agentprobe-demo-agents.onrender.com` | Woken before a run or connection test. |
| `QUEUE_BACKEND` | `inline` | Runs execute in the API process; there's no worker or Redis. |
| `RATE_LIMIT_BACKEND` | `memory` | One process. The buckets reset when it sleeps, which happens only after it's idle. |
| `INLINE_MAX_RUNS` | `2` | Runs executing at once. |
| `COOKIE_SECURE` | `1` | ADR 0009. The API refuses to start with `0` when `WEB_ORIGIN` is https. |
| `LOG_LEVEL` | `INFO` | |
| `SIGNUP_OPEN` | `1` | Anyone may register, bounded by the limits below. |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | Per client IP, shared by register and login. |
| `REGISTER_RATE_LIMIT_PER_HOUR` | `5` | Per client IP. |
| `MAX_SIGNUPS_PER_DAY` | `200` | All users, rolling 24 h. |
| `MAX_PROJECTS_PER_USER` | `3` | |
| `MAX_AGENTS_PER_USER` | `5` | |
| `MAX_CASES_PER_SUITE` | `50` | |
| `MAX_RUNS_PER_USER_PER_DAY` | `30` | Rolling 24 h. Counts server runs and CI reports. |
| `LLM_PROVIDER` | `mock` | Mock judges. Live Gemini is an opt-in (below). |
| `RUN_LIVE` | `0` | |
| `LLM_BUDGET_USD_PER_RUN` | `0.10` | Per LLM client; a live run has at most two (judges, clustering). |
| `LLM_GLOBAL_USD_PER_DAY` | `1.00` | Each live run reserves 2 x `LLM_BUDGET_USD_PER_RUN`, so at most 5 live runs per rolling 24 h. |
| `ALLOW_PRIVATE_TARGETS` | `0` | No private targets. Leave `PRIVATE_TARGET_ALLOWLIST` unset: an entry there is a private-address exception, and the demo agents are public. |

Leave `API_EXTRAS` unset (it's the live-Gemini opt-in). Render sets `RENDER_GIT_COMMIT` itself, and `/ready` reports it.

The rest take their code defaults, which suit production:
- `JWT_TTL_MINUTES=15`, `REFRESH_TTL_DAYS=30`
- `RATE_LIMIT_PER_MINUTE=120` (per API key)
- `RUN_CONCURRENCY=4`, `RUN_MAX_RETRIES=2`, `RUN_BACKOFF_BASE_S=1.0`, `RUN_STALE_AFTER_S=600`
- `EMBEDDING_DIM=768`
- `SIGNUP_ALLOWED_EMAILS` empty (unused while `SIGNUP_OPEN=1`)
- the `LLM_*` rate and budget knobs in `.env.example`

The image sets `AGENTPROBE_CONFIG_DIR=/app/config` and `AGENTPROBE_STATE_DIR=/tmp/agentprobe`.

### Demo agents environment
The service has no secrets and no database.

| Variable | Value | Why |
|---|---|---|
| `PORT` | `9000` | The port the image's uvicorn listens on. |
| `AGENT_MODE` | `mock` | Rule-based; never an LLM. No provider key is ever set here. |
| `FLAKY_RATE` | `0.2` | Seeded order-lookup failures (`FLAKY_SEED` defaults to 1337). |

Every response carries `X-AgentProbe-Demo: Deliberately vulnerable demo with planted flaws. No real data: fake data only.`, and `GET /` says the same.

## Web (Vercel project, Production environment)

| Variable | Value | When it's read |
|---|---|---|
| `API_INTERNAL_URL` | The API's Render URL, e.g. `https://agentprobe-api.onrender.com` | At runtime, by `src/proxy.ts` for every `/api/*` request |
| `NEXT_PUBLIC_API_URL` | The same URL | At build time: where the browser opens a run's live progress stream (ADR 0031) |
| `PROXY_SECRET` | The API's `PROXY_SECRET` (mark it Sensitive) | At runtime, by `src/proxy.ts` |

Project settings:
- **Root Directory:** `apps/web`, with "Include files outside the root directory" on (the default). The pnpm lockfile is at the repo root.
- **Framework:** Next.js.
- **Node.js:** 22.x.

`apps/web/vercel.json` turns off Vercel's own Git deploys, so production only changes through `deploy.yml`, after CI passes.

## GitHub Actions
The environment named `production` holds these **secrets**:

| Secret | Value |
|---|---|
| `PRODUCTION_DATABASE_URL` | Same as the API's `DATABASE_URL` (the migrations run from the runner). |
| `RENDER_API_DEPLOY_HOOK` | The API service's Deploy Hook URL (Settings > Deploy Hook). It's a credential: anyone holding it can trigger a deploy. |
| `RENDER_DEMO_DEPLOY_HOOK` | The demo agents service's Deploy Hook URL. |
| `VERCEL_TOKEN` | A Vercel access token. |

These are **repository variables** (Settings > Secrets and variables > Actions > Variables):

| Variable | Value |
|---|---|
| `DEPLOY_ENABLED` | `true` arms deploy.yml. It has to be a repository variable: the job's `if` is evaluated before the environment is loaded. |
| `API_URL` | The API's Render URL, no trailing slash. deploy.yml waits on its `/ready`. |
| `WEB_ORIGIN` | The Vercel production URL, no trailing slash. |
| `VERCEL_ORG_ID` | The Vercel team or account ID. |
| `VERCEL_PROJECT_ID` | The Vercel project ID. |

## Client IPs, the proxy, and cookies
Per-IP limits (login, registration) need the browser's real IP:
- **Browser → Vercel → API.** Vercel's edge overwrites `X-Forwarded-For` with the real client. `src/proxy.ts` replaces it with exactly that address and adds `x-agentprobe-proxy-secret`. Vercel's rewrite and Render's edge then append their own entries, so the API takes the **leftmost** entry, and only when the secret matches (a constant-time compare). A browser's own copy of the secret header is dropped.
- **Everything else** (CLI, GitHub Action, the live-progress stream, a spoofed header without the secret) is keyed on the connecting address, which on Render is Render's proxy. Those callers authenticate with API keys or a 60 s stream token, and the per-IP limits only guard register and login.
- **No platform header is trusted**, and uvicorn runs with `--no-proxy-headers`.

Cookies (checked against ADR 0009):
- `access_token` is `HttpOnly; Secure; SameSite=Lax; Path=/`, and `refresh_token` is `HttpOnly; Secure; SameSite=Strict; Path=/`.
- Neither has a `Domain` attribute. They're set through the `/api` proxy, so they're host-only cookies on the Vercel domain and never sent to `*.onrender.com`.
- Cookie-authenticated mutations, and register and login, need `Origin` equal to `WEB_ORIGIN`, so open the site at exactly that URL.
- `COOKIE_SECURE=0` with an https `WEB_ORIGIN` refuses to start.

## Live Gemini (opt-in)
Mock judges are the default. To judge with Gemini, on the API service in Render:
1. Set `API_EXTRAS=live`. Render passes environment variables to the Docker build as build args, so the image then includes LiteLLM. CI builds that variant on every push.
2. Set `GEMINI_API_KEY`, `LLM_PROVIDER=litellm` and `RUN_LIVE=1`, and check `LLM_BUDGET_USD_PER_RUN` and `LLM_GLOBAL_USD_PER_DAY`.
3. Save, rebuild and deploy. Then check memory under a live run against the 512 MB limit.

Only runs started with `mock: false` (and CI reports with `mock: false`, which cluster with the LLM) call Gemini. `LLM_GLOBAL_USD_PER_DAY` refuses a live run once the worst case of the last 24 hours would pass it. Only send fake data (CLAUDE.md).

## Manual steps
Do these in order. None of them asks for a card. Where a name is taken, use the one you get, and carry it through the later steps.

1. **Neon production database.** In the Neon console, create a project `agentprobe-prod`: Postgres 18, AWS `ap-southeast-1` (Singapore). If the free plan won't create a second project, add a branch `production` to the existing project instead; it then shares that project's compute quota. Under Connect, turn **Connection pooling off** and copy the connection string. Keep it as `<NEON_URL>`.
2. **Secrets.** From the repo root:
   ```bash
   uv run python -c "import secrets; print('JWT_SECRET', secrets.token_urlsafe(48)); print('PROXY_SECRET', secrets.token_urlsafe(48))"
   uv run python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY', Fernet.generate_key().decode())"
   ```
   Store all three somewhere durable, `ENCRYPTION_KEY` especially: without it, stored agent auth headers can't be decrypted.

   Then migrate the new database once from here, so the API's first deploys start cleanly. The API checks for unfinished runs at startup, so it needs the tables:
   ```bash
   DATABASE_URL='<NEON_URL>' uv run alembic -c apps/api/alembic.ini upgrade head
   ```
3. **Render account.** At https://dashboard.render.com, sign up with **GitHub**, choose the free plan, and give Render's GitHub app access to this repository.
4. **Demo agents service.** New > Web Service > this repository, with the demo agents column of [Render services](#render-services). That's name `agentprobe-demo-agents`, Docker, branch `main`, region Singapore, Root Directory empty, Dockerfile Path `./demo-agents/Dockerfile`, build context `.`, Docker Command empty, instance type Free, Health Check Path `/health`, Auto-Deploy Off.
   - Environment: `PORT=9000`, `AGENT_MODE=mock`, `FLAKY_RATE=0.2`.
   - Create it. Note its URL as `<DEMO_URL>` (e.g. `https://agentprobe-demo-agents.onrender.com`) and its hostname as `<DEMO_HOST>`.
   - Under Settings > Deploy Hook, copy the URL as `<DEMO_HOOK>`.
5. **API service.** New > Web Service > this repository, with the API column of [Render services](#render-services). That's name `agentprobe-api`, Docker, branch `main`, region Singapore, Root Directory empty, Dockerfile Path `./apps/api/Dockerfile`, build context `.`, Docker Command `uvicorn agentprobe_api.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers`, instance type Free, Health Check Path `/ready`, Auto-Deploy Off.
   - Environment: every row of [API environment](#api-environment). `DATABASE_URL=<NEON_URL>`, the three secrets from step 2, `WAKE_TARGET_HOSTS=<DEMO_HOST>`. Set `WEB_ORIGIN` and `PUBLIC_WEB_URL` to `https://placeholder.invalid` for now: step 7 sets them.
   - Create it. Render builds and starts it straight away. Note its URL as `<API_URL>`.
   - Under Settings > Deploy Hook, copy the URL as `<API_HOOK>`.
6. **Vercel project.** In the Vercel dashboard, Add New > Project > import this repository.
   - Root Directory `apps/web`, Framework Next.js, Node 22.
   - Environment Variables (Production): `API_INTERNAL_URL=<API_URL>`, `NEXT_PUBLIC_API_URL=<API_URL>`, `PROXY_SECRET=<from step 2>` (mark it Sensitive).
   - Deploy once (deploy.yml replaces this build), and note the production URL as `<WEB_ORIGIN>` (e.g. `https://agentprobe-xyz.vercel.app`).
   - Note the Project ID (Settings > General) and the Team or Account ID (team Settings > General).
   - Create an access token (Account Settings > Tokens).
7. **Point the API at the web app.** In Render, on the API's Environment, set `WEB_ORIGIN=<WEB_ORIGIN>` and `PUBLIC_WEB_URL=<WEB_ORIGIN>`, then Save, rebuild and deploy.
8. **GitHub secrets and variables.**
   - Settings > Environments > New environment `production`, with the secrets `PRODUCTION_DATABASE_URL=<NEON_URL>`, `RENDER_API_DEPLOY_HOOK=<API_HOOK>`, `RENDER_DEMO_DEPLOY_HOOK=<DEMO_HOOK>` and `VERCEL_TOKEN=<from step 6>`.
   - Settings > Secrets and variables > Actions > Variables: `API_URL=<API_URL>`, `WEB_ORIGIN=<WEB_ORIGIN>`, `VERCEL_ORG_ID=<from step 6>` and `VERCEL_PROJECT_ID=<from step 6>`.
9. **Arm and run.** Add the repository variable `DEPLOY_ENABLED=true`, then Actions > Deploy > Run workflow on `main`. It migrates, deploys both services, waits for `<API_URL>/ready` to report the commit, and deploys the web app. From then on, every push to `main` that passes CI deploys.
10. **Check.**
    - Run `curl <API_URL>/ready`. It returns `{"status":"ready","commit":"<sha>"}`, after up to a minute if the API was asleep.
    - Open `<WEB_ORIGIN>` with the API asleep (15 idle minutes). The "Waking the server" notice shows, then the page loads.
    - Run the production smoke test from the repo root. It wakes both services and prints how long each took (record those cold starts in docs/PROGRESS.md). It then registers a throwaway user through the web proxy, tests and runs an agent on the public demo agents, checks results, a trace, findings and a share link, and deletes the user from the production database afterwards, even when a check fails:
      ```bash
      WEB_ORIGIN=<WEB_ORIGIN> API_URL=<API_URL> DEMO_AGENTS_URL=<DEMO_URL> \
      PRODUCTION_DATABASE_URL='<NEON_URL>' uv run python scripts/smoke_prod.py
      ```
      It ends with `PASS production smoke test`, and uses one of your IP's five hourly registrations.
    - Then work through ADR 0036's "Unverified until the first live deploy" list, starting with the `X-Forwarded-For` check.
