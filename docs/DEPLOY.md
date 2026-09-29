# Deploying AgentProbe

The production demo ([ADR 0035](decisions/0035-production-deploy-on-fly-and-vercel.md)):

| Service | Where | Notes |
|---|---|---|
| Web (Next.js) | Vercel, Hobby | Forwards `/api/*` to the API (`src/proxy.ts`) with the proxy secret and the browser's IP. |
| API | Fly.io app, one `shared-cpu-1x` 512 MB machine, region `sin` | `QUEUE_BACKEND=inline`, no Redis. Stops when idle and starts on the next request. |
| Demo agents | Fly.io app, one 256 MB machine | Deliberately vulnerable, fake data only. No public IP: reachable only as `<app>.flycast` from the API. Stops when idle. |
| Postgres | Neon, its own project (Free), AWS `ap-southeast-1` | Separate from the dev and test branches' project, so it has its own compute quota. |

There's no Redis in production. The Redis queue path is proven by CI's `docker` job instead (ADR 0033).

`.github/workflows/deploy.yml` deploys, after CI passes on `main`, on the commit CI tested:
1. migrations;
2. the demo agents;
3. the API, then a check that `/ready` answers;
4. the web app;
5. a check that `https://<web>/api/health` reaches the API.

It does nothing until the repository variable `DEPLOY_ENABLED` is `true`.

## Health and readiness
| Endpoint | Meaning | Used by |
|---|---|---|
| API `GET /health` | The process answers. Touches nothing else. | Compose healthcheck |
| API `GET /ready` | The database answers too (`SELECT 1`); 503 otherwise. | Fly's health check, and deploy.yml after the API deploy |
| Demo agents `GET /health` | The process answers. | Fly's health check, compose healthcheck |

## Environment variables

### API (Fly app, default name `agentprobe-api`)
Set in `fly.api.toml` `[env]` (committed; a change is a reviewed commit):

| Variable | Value | Why |
|---|---|---|
| `QUEUE_BACKEND` | `inline` | Runs execute in the API process; there's no worker or Redis. |
| `RATE_LIMIT_BACKEND` | `memory` | One process. The buckets reset only when the machine stops, which happens only after it's idle. |
| `INLINE_MAX_RUNS` | `2` | Runs executing at once. |
| `CLIENT_IP_HEADER` | `Fly-Client-IP` | Fly's proxy sets it to the address it accepted the connection from. |
| `FORWARDED_ALLOW_IPS` | `172.16.0.0/12` | The range Fly's proxy reaches the machine from. `CLIENT_IP_HEADER` is trusted only from these peers. |
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
| `LLM_GLOBAL_USD_PER_DAY` | `1.00` | Each live run reserves 2 x `LLM_BUDGET_USD_PER_RUN`, so this allows at most 5 live runs per rolling 24 h. |
| `ALLOW_PRIVATE_TARGETS` | `0` | No private targets except those on `PRIVATE_TARGET_ALLOWLIST`. |

Set by `deploy.yml` with `flyctl deploy --env`, from GitHub variables:

| Variable | Value |
|---|---|
| `WEB_ORIGIN` | The Vercel production URL, e.g. `https://agentprobe.vercel.app`. The Origin check and the SSE route's CORS both use it. |
| `PUBLIC_WEB_URL` | Same as `WEB_ORIGIN`: links in exports and PR comments. |
| `PRIVATE_TARGET_ALLOWLIST` | `<demo agents app>.flycast`, the only private host agents may target. |

Set once with `fly secrets set` (never committed):

| Secret | Value |
|---|---|
| `DATABASE_URL` | The Neon production connection string: the **direct** host (no `-pooler`), with `sslmode=require&channel_binding=require`. Paste Neon's string as-is. |
| `JWT_SECRET` | 32+ random characters. |
| `ENCRYPTION_KEY` | A Fernet key. It encrypts stored agent auth headers: losing it makes them unreadable, and rotating it needs a re-encryption (ADR 0003). |
| `PROXY_SECRET` | 32+ random characters. **The same value** as the Vercel project's `PROXY_SECRET`. |

The rest take their code defaults, which suit production:
- `JWT_TTL_MINUTES=15`, `REFRESH_TTL_DAYS=30`
- `RATE_LIMIT_PER_MINUTE=120` (per API key)
- `RUN_CONCURRENCY=4`, `RUN_MAX_RETRIES=2`, `RUN_BACKOFF_BASE_S=1.0`, `RUN_STALE_AFTER_S=600`
- `EMBEDDING_DIM=768`
- `SIGNUP_ALLOWED_EMAILS` empty (unused while `SIGNUP_OPEN=1`)
- the `LLM_*` rate and budget knobs in `.env.example`

The image sets `AGENTPROBE_CONFIG_DIR=/app/config` and `AGENTPROBE_STATE_DIR=/tmp/agentprobe`.

### Demo agents (Fly app, default name `agentprobe-demo-agents`)
All in `fly.demo-agents.toml`. The app has no secrets and no database.

| Variable | Value | Why |
|---|---|---|
| `AGENT_MODE` | `mock` | Rule-based; never an LLM. |
| `FLAKY_RATE` | `0.2` | Seeded order-lookup failures (`FLAKY_SEED` defaults to 1337). |

Every response carries `X-AgentProbe-Demo: Deliberately vulnerable test targets with planted flaws. Fake data only.`, and `GET /` says the same.

### Web (Vercel project, Production environment)

| Variable | Value | When it's read |
|---|---|---|
| `API_INTERNAL_URL` | `https://<api app>.fly.dev` | At runtime, by `src/proxy.ts` for every `/api/*` request |
| `NEXT_PUBLIC_API_URL` | `https://<api app>.fly.dev` | At build time: where the browser opens a run's live progress stream (ADR 0031) |
| `PROXY_SECRET` | The API's `PROXY_SECRET` (mark it Sensitive) | At runtime, by `src/proxy.ts` |

Project settings:
- **Root Directory:** `apps/web`, with "Include files outside the root directory" on (the default). The pnpm lockfile is at the repo root.
- **Framework:** Next.js.
- **Node.js:** 22.x.

`apps/web/vercel.json` turns off Vercel's own Git deploys, so production only changes through `deploy.yml`, after CI passes.

### GitHub Actions
The environment named `production` holds these **secrets**:

| Secret | Value |
|---|---|
| `PRODUCTION_DATABASE_URL` | Same as the API's `DATABASE_URL` (the migrations run from the runner). |
| `FLY_API_TOKEN` | A Fly org deploy token (it deploys both apps). |
| `VERCEL_TOKEN` | A Vercel access token. |

These are **repository variables** (Settings > Secrets and variables > Actions > Variables):

| Variable | Value |
|---|---|
| `DEPLOY_ENABLED` | `true` arms deploy.yml. It has to be a repository variable: the job's `if` is evaluated before the environment is loaded. |
| `FLY_API_APP` | The API's Fly app name. |
| `FLY_DEMO_AGENTS_APP` | The demo agents' Fly app name. |
| `WEB_ORIGIN` | The Vercel production URL, no trailing slash. |
| `VERCEL_ORG_ID` | The Vercel team or account ID. |
| `VERCEL_PROJECT_ID` | The Vercel project ID. |
| `API_EXTRAS` | Empty. `live` only for the live-Gemini opt-in. |

## Client IPs, the proxy, and cookies
Per-IP limits (login, registration) need the browser's real IP, and neither hop can be trusted by address alone:
- **Browser → Vercel → API.** Vercel overwrites `X-Forwarded-For` with the real client, but its egress IPs aren't published, so the API can't recognize Vercel by address. `src/proxy.ts` therefore sends `x-agentprobe-proxy-secret` and `x-agentprobe-client-ip`. The API uses that IP only when the secret matches (a constant-time compare); a browser's own copies of either header are dropped.
- **CLI, GitHub Action, live-progress stream → API directly.** Fly's proxy sets `Fly-Client-IP`. The API trusts it only from a `FORWARDED_ALLOW_IPS` peer and runs uvicorn with `--no-proxy-headers`. That's because Fly appends to `X-Forwarded-For`: its left entries are whatever the client sent, and its rightmost is Fly's own.
- **Only through the proxy.** The API machine binds 0.0.0.0 (IPv4), so only Fly's proxy reaches it; Fly's private IPv6 network can't. The API's public URL has to stay reachable for the stream (a 60 s single-run token) and the CLI (API keys). IP trust flows only through the two headers above.

Cookies (checked against ADR 0009):
- `access_token` is `HttpOnly; Secure; SameSite=Lax; Path=/`, and `refresh_token` is `HttpOnly; Secure; SameSite=Strict; Path=/`.
- Neither has a `Domain` attribute. They're set through the `/api` proxy, so they're host-only cookies on the Vercel domain and never sent to `*.fly.dev`.
- Cookie-authenticated mutations, and now register and login too, need `Origin` equal to `WEB_ORIGIN`, so open the site at exactly that URL.
- `COOKIE_SECURE=0` with an https `WEB_ORIGIN` refuses to start.

## Live Gemini (opt-in)
Mock judges are the default. To judge with Gemini:
1. Set the repository variable `API_EXTRAS=live`. The API image then includes LiteLLM; CI builds that variant on every push.
2. Run `fly secrets set -a <api app> GEMINI_API_KEY=...`.
3. In a reviewed commit, set `LLM_PROVIDER = "litellm"` and `RUN_LIVE = "1"` in `fly.api.toml`, and check `LLM_BUDGET_USD_PER_RUN` and `LLM_GLOBAL_USD_PER_DAY`.

Only runs started with `mock: false` (and CI reports with `mock: false`, which cluster with the LLM) call Gemini. `LLM_GLOBAL_USD_PER_DAY` refuses a live run once the worst case of the last 24 hours would pass it. Only send fake data (CLAUDE.md).

## Manual steps
Do these in order. Replace `agentprobe-api`, `agentprobe-demo-agents` and the Vercel URL with the names you actually get (Fly app names are global).

1. **Neon production project.** In the Neon console, create a new project `agentprobe-prod`: Postgres 18, AWS `ap-southeast-1` (Singapore). From Connect, copy the connection string for the **direct** host (turn off "Connection pooling"). Keep it for steps 4 and 7. Migrations run from deploy.yml; nothing else is needed here.
2. **Generate the secrets** locally, from the repo root:
   ```bash
   uv run python -c "import secrets; print('JWT_SECRET', secrets.token_urlsafe(48)); print('PROXY_SECRET', secrets.token_urlsafe(48))"
   uv run python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY', Fernet.generate_key().decode())"
   ```
   Store `ENCRYPTION_KEY` somewhere durable. Without it, stored agent auth headers can't be decrypted.
3. **Fly account and apps.** Install flyctl, run `fly auth login`, and add a card (Fly has no free tier). Then:
   ```bash
   fly apps create agentprobe-api
   fly apps create agentprobe-demo-agents
   fly ips allocate-v6 --private -a agentprobe-demo-agents   # its only address: <app>.flycast
   ```
4. **API secrets.** `--stage` because the app has no machines yet:
   ```bash
   fly secrets set --stage -a agentprobe-api \
     DATABASE_URL='<Neon direct connection string>' \
     JWT_SECRET='<from step 2>' ENCRYPTION_KEY='<from step 2>' PROXY_SECRET='<from step 2>'
   ```
5. **Fly deploy token** for GitHub: `fly tokens create org --name agentprobe-github`. Keep the output for step 7.
6. **Vercel project.** In the Vercel dashboard: Add New > Project > import this GitHub repository.
   - Root Directory `apps/web`, Framework Next.js, Node 22.
   - Under Environment Variables (Production), add `API_INTERNAL_URL=https://agentprobe-api.fly.dev`, `NEXT_PUBLIC_API_URL=https://agentprobe-api.fly.dev` and `PROXY_SECRET=<from step 2>` (mark it Sensitive).
   - Deploy once. The import's first build can fail or point at an API that isn't up yet; deploy.yml replaces it.
   - Note the production URL (e.g. `https://agentprobe-xyz.vercel.app`) as `WEB_ORIGIN`.
   - Note the Project ID (Settings > General) and your Team/Account ID (team Settings > General).
   - Create an access token (Account Settings > Tokens).
7. **GitHub.** Settings > Environments > New environment `production`. Add the secrets `PRODUCTION_DATABASE_URL` (the step 1 string), `FLY_API_TOKEN` (step 5) and `VERCEL_TOKEN` (step 6). Then, under Settings > Secrets and variables > Actions > Variables, add the repository variables:
   - `FLY_API_APP=agentprobe-api`
   - `FLY_DEMO_AGENTS_APP=agentprobe-demo-agents`
   - `WEB_ORIGIN=<step 6 URL>`
   - `VERCEL_ORG_ID=<step 6>`
   - `VERCEL_PROJECT_ID=<step 6>`
   - `API_EXTRAS=` (leave empty)
8. **Arm and run.** Add the repository variable `DEPLOY_ENABLED=true`. Then go to Actions > Deploy > Run workflow on `main`. From then on, every push to `main` that passes CI deploys.
9. **Check.**
   - `fly ips list -a agentprobe-demo-agents` shows only a private IPv6.
   - `curl https://agentprobe-api.fly.dev/ready` returns `{"status":"ready"}`.
   - Open `WEB_ORIGIN` and register. Add an agent named `support-v1` (the smoke suite's `agent:`) at `http://agentprobe-demo-agents.flycast/support/v1/chat` with "Allow private targets" checked, upload `suites/examples/smoke.yaml` and run it.
