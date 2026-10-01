# AgentProbe

## Run a suite locally

No server, database or queue needed. Start the bundled demo agents (mock mode, port 9000), then run the smoke suite against them. The agents are configured in `agentprobe.yaml`.

```bash
uv run python -m agentprobe_demo_agents                                          # terminal 1
uv run agentprobe run suites/examples/smoke.yaml --fail-under 0.9               # /support/v1
uv run agentprobe run suites/examples/smoke.yaml --agent vulnerable             # planted flaws: exit 1
uv run agentprobe baseline set .agentprobe/runs/<v1-run>.json                    # save as "main"
uv run agentprobe run suites/examples/smoke.yaml --agent support-v2 --baseline main  # exit 2
uv run agentprobe run suites/examples/mcp-safety.yaml --agent mcp-tools         # MCP adapter, planted flaws
```

Every run is saved to `.agentprobe/runs/`. `agentprobe compare <a> <b>` diffs two runs. The exit codes are `0` passed, `1` below `--fail-under` (default 1.0), `2` regression, `3` usage/config error and `4` infrastructure error; `agentprobe --help` lists them. `agentprobe init` scaffolds `agentprobe.yaml` and an example suite for your own agent.

## Run the whole stack with Docker

Needs Docker Engine 25+ with Compose v2, and nothing else: no API keys, no `.env`. `docker-compose.yml` starts Postgres (pgvector), Redis, the API (it migrates the database on start), the worker, the dashboard and the demo agents. The LLM is the offline mock, and runs go through the Redis queue to the worker. CI's `docker` job runs exactly these commands:

```bash
docker compose build
docker compose up -d --wait              # returns once every healthcheck passes
python3 scripts/compose_smoke.py          # registers smoke@example.com, runs suites/examples/smoke.yaml, prints the pass rate
docker compose down -v                    # stop, and delete the database volume
```

Before `down`, open http://localhost:3000 (`localhost`, not `127.0.0.1`: the API only accepts that origin) and register as `demo@example.com`. That address and `smoke@example.com` are the only two allowed to sign up. The demo agents are reachable from the stack at `http://demo-agents:9000` (for example `http://demo-agents:9000/support/v1/chat`, with "Allow private targets" checked, which is the default) and aren't published to your machine. The API is also on http://localhost:8000.

The compose file is for local use only. Its secrets are committed, so they're public, and its ports bind to 127.0.0.1.

## Deploy

Live (the first request after a quiet spell takes about a minute while the free services wake):

| | URL |
|---|---|
| Web app | https://agent-probe-umber.vercel.app |
| API (`/ready`, `/docs`) | https://agentprobe-api-1uno.onrender.com |
| Demo agents (deliberately vulnerable, fake data only) | https://agentprobe-1r00.onrender.com |

The production demo runs on free tiers that need no card: Vercel Hobby (web), two Render free web services (the API and the demo agents) and Neon Free (Postgres). Free services sleep when idle, so the first visit after a quiet spell waits about a minute while the API wakes. [docs/DEPLOY.md](docs/DEPLOY.md) lists every environment variable and dashboard setting per service, and the one-time manual steps. After that, every push to `main` that passes CI deploys through `.github/workflows/deploy.yml`.

## Database

AgentProbe uses Postgres with pgvector. Locally that's Neon branches: one for development (`DATABASE_URL`) and a separate one for integration tests (`TEST_DATABASE_URL`).

The expected format (psycopg 3 driver, TLS):

```
postgresql+psycopg://USER:PASSWORD@ep-XXXX-XXXX.REGION.aws.neon.tech/DBNAME?sslmode=require&channel_binding=require
```

Converting the connection string Neon gives you (Dashboard → Connect):
- Neon shows `postgresql://USER:PASSWORD@ep-…neon.tech/DBNAME?sslmode=require&channel_binding=require`.
- You can paste it **as-is**. The app rewrites `postgresql://` (or `postgres://`) to `postgresql+psycopg://`. You can also change the scheme yourself.
- Keep `sslmode=require` and `channel_binding=require`. If a remote URL has no `sslmode`, the app adds `sslmode=require`.
- Use the **direct** host, the one without `-pooler` in its name.
- `TEST_DATABASE_URL` must point at a different branch than `DATABASE_URL`. Integration tests also refuse to run unless `ALLOW_DB_TESTS=1`.

Commands:
- `pnpm db:migrate`: apply migrations to `DATABASE_URL`.
- `pnpm verify`: `pnpm check`, then integration tests on `TEST_DATABASE_URL`.

Both load `.env`. The first connection after Neon has been idle can take a few seconds while the compute wakes up.
