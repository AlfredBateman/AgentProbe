# Progress

## Done
- 2026-09-24 **Bootstrap**:
  - PLAN.md, CLAUDE.md, ADR 0001 (packages/core), ADR 0002 (web toolchain versions).
  - Monorepo scaffold:
    - uv workspace on Python 3.12: `packages/core`, `packages/cli`, `apps/api`, `demo-agents`.
    - pnpm workspace: `apps/web`, running Next 16.3.6, React 19.3, Tailwind 4.3.
  - `GET /health`.
  - One test each in core, api and web; `pnpm check` is green.
  - DB-test guard in the root `conftest.py`.

- 2026-09-25 **All six PLAN.md questions resolved** (Q1–Q6). ADR 0003 (secret storage), ADR 0004 (font substitution), ADR 0005 (drop React Flow), ADR 0006 (statistics methodology). PLAN.md §2, §3, §4, §5 updated to record the decisions; no more open questions block any phase.

- 2026-09-25 **A1–A3: data layer, migrations, test infra, CI**:
  - `apps/api`: pydantic-settings (`settings.py`), and the psycopg 3 async engine tuned for Neon (`db.py`: URL normalization, TLS default, pre-ping, recycle, 10 s connect timeout).
  - SQLAlchemy 2.0 models for every SPEC §7 table, plus the PLAN §3 changes and `run_case_summaries` / `secrets` ([ADR 0007](decisions/0007-data-model-additions.md)).
  - Alembic (sync) `0001_initial`, which starts with `CREATE EXTENSION IF NOT EXISTS vector`. Applied to the Neon dev branch.
  - `SecretBox` (Fernet) for the `secrets` table; decrypted values come back as `SecretStr`.
  - Integration fixtures: migrate once per session, rollback-per-test isolation ([ADR 0008](decisions/0008-db-connection-and-test-isolation.md)).
  - Tests:
    - migration round-trip, drift and FK-index coverage;
    - constraints and isolation;
    - DB guard proven via pytester (the guard now compares host/port/db, not raw strings);
    - a redis PING in CI.
  - `.github/workflows/ci.yml`: a python job (pgvector pg18 + redis 8 service containers, `pytest -m "not live"`) and a web job; uv and pnpm caching, a concurrency group, job timeouts.
  - README "Database" section: the DATABASE_URL format and how to convert Neon's string.

## Next
- A4: users, register/login/logout, JWT cookie, signup allowlist. First DB-backed endpoint: add the session dependency and handle the Windows selector loop for uvicorn.
- A5: projects CRUD + project API keys.
- B1.1: suite YAML schema — first task that needs the statistics config surface from ADR 0006 (`statistics:` block) plumbed through.

## Decisions
- The user approved PLAN.md §2 items 1–6 and 8 (immutable case rows, ingest/baseline endpoints, same-origin cookie auth, signup allowlist + budget guard, case-level judgments, share links, separate judge cost).
- TypeScript 5.9 / ESLint 9 instead of 7 / 10 ([ADR 0002](decisions/0002-web-toolchain-versions.md)).
- `agents.secret_ref` references a new `secrets` table, Fernet-encrypted, write-only ([ADR 0003](decisions/0003-secret-storage.md)). Unblocks B2.1.
- Display font: Geist; monospace: Geist Mono; body: Inter Variable (unchanged) ([ADR 0004](decisions/0004-font-substitution.md)).
- Trace timeline: plain HTML/CSS, no React Flow ([ADR 0005](decisions/0005-trace-timeline-no-react-flow.md)).
- Regression statistics: Fisher exact + Holm (per case), paired sign-flip permutation (suite), case-level bootstrap CI; α=0.05, min_drop=0.05, all configurable via suite YAML and CLI flags ([ADR 0006](decisions/0006-statistics-methodology.md)).
- Hosting for the API/worker (Q2) is deliberately deferred to Phase F4; the only binding constraint now is that the worker stays behind the `QueueBackend` interface with `inline` as the local default.
- `packages/core` must contain exactly one run-execution implementation (`execute_attempt` / `finalize_run` / `run_suite`), shared by the CLI's local run and the server runner — no duplicate run loops (Q6 requirement, tracked at B1.7).
- Share links store only `runs.share_token_hash` (SHA-256), not a plaintext token. The Fernet key env var stays `ENCRYPTION_KEY` (user decisions, 2026-09-25).
- Data model conventions: UUID PKs, text+CHECK instead of PG enums, `NUMERIC(12,6)` costs, CASCADE along ownership, and every FK covered by a leading index ([ADR 0007](decisions/0007-data-model-additions.md)).
- Neon connection config, sync migrations, rollback-per-test isolation, selector loop on Windows, CI on service containers ([ADR 0008](decisions/0008-db-connection-and-test-isolation.md)).

## Known issues
- `pnpm verify` needs `TEST_DATABASE_URL`, `DATABASE_URL` and `ALLOW_DB_TESTS=1` (loaded from `.env`). Without them it refuses with exit code 2, which is intended. It takes about 45 s against Neon, mostly the migration round-trip.
- On native Windows, psycopg async needs `SelectorEventLoop`. Tests handle this in the root conftest; `pnpm dev:api` still needs it once A4 opens DB connections.
- `uv` and `gh` are installed but not on PATH in some shells (`%USERPROFILE%\.local\bin`, `C:\Program Files\GitHub CLI`).
- The pytest run shows a `StarletteDeprecationWarning`: Starlette's TestClient wants `httpx2` instead of `httpx`. Swapping `httpx==0.28.1` for `httpx2` was blocked by a local permission rule this session. Redo it once allowed.
- `next build` downloads Google Fonts (Inter, Geist), so it needs network access. `pnpm check` doesn't build.
