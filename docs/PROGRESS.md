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

- 2026-09-25 **A4–A5: auth, projects, API keys, rate limits, errors, logging** ([ADR 0009](decisions/0009-session-scheme.md)):
  - `POST /auth/register|login|refresh|logout`:
    - argon2id, with hashing off the event loop and a dummy verify for unknown emails;
    - `EmailStr` validation and the signup allowlist;
    - a 15-minute httpOnly access cookie, plus a hashed, rotating refresh cookie with reuse detection.
  - CSRF: SameSite, plus `Origin == WEB_ORIGIN` on cookie mutations, plus FastAPI's strict JSON content type.
  - `GET/POST /projects` and `GET /projects/{id}`. Project API keys: create (shown once), list (`last4`) and revoke (soft, via `revoked_at`); `last_used_at` is recorded on use.
  - One `get_principal` dependency for session or `Bearer ap_…`. A key is scoped to one project and can't manage the account.
  - Ownership: everything goes through `owned_project`, and other users' resources are 404, indistinguishable from nonexistent.
  - `RateLimiter` token buckets: in-memory by default; Redis (a Lua script) runs in CI. Limits per API key and per IP on register/login, with 429 + `Retry-After`.
  - Errors use one JSON shape with `request_id`, and validation details never echo input. Pure-ASGI request-ID middleware; JSON logs with a handler-level `RedactFilter`.
  - Stream token type (`typ=stream`) and its non-interchangeability with access tokens are tested; the endpoint lands in B2.4.
  - Tests:
    - `tests/idor.py`, a reusable IDOR helper (extend `test_idor.PROBES` for every new endpoint);
    - invalid, expired and forged tokens;
    - refresh reuse; revoked keys;
    - rate limits (both backends);
    - an end-to-end log-capture test with SQL logging on.
  - Migration 0002 (`refresh_tokens`, `api_keys.last4/created_at/revoked_at`) applied to the Neon dev branch.
## Next
- B1.1: suite YAML schema — first task that needs the statistics config surface from ADR 0006 (`statistics:` block) plumbed through.

## Decisions
- Session scheme: an httpOnly access cookie (not a JS token) behind the Next.js `/api` rewrite; a rotating refresh cookie; an SSE stream-token fallback; API keys only in `Authorization`; token-bucket rate limits with memory/Redis backends ([ADR 0009](decisions/0009-session-scheme.md)). Amends PLAN §2 #3 and supersedes #20.
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
- `pnpm verify` needs `TEST_DATABASE_URL`, `DATABASE_URL` and `ALLOW_DB_TESTS=1` (loaded from `.env`). Without them it refuses with exit code 2, which is intended. It takes about 2.5 min against Neon from here: each request costs 2–4 round trips of 80–140 ms (more on a bad network day). A Neon region closer to the developer would cut this proportionally.
- On native Windows, psycopg async needs `SelectorEventLoop`. Tests use the root conftest hook; `pnpm dev:api` passes `--loop asyncio:SelectorEventLoop`. Production start commands on Windows would need the same flag (Linux doesn't).
- Deploy (F4) must set `FORWARDED_ALLOW_IPS` to the proxy and keep the API reachable only through it. Otherwise the per-IP auth limit is either global (every user shares the proxy's IP) or spoofable (ADR 0009 §9).
- `JWT_TTL_MINUTES` now defaults to 15. A local `.env` that still says 60 keeps 60-minute access cookies.
- `uv` and `gh` are installed but not on PATH in some shells (`%USERPROFILE%\.local\bin`, `C:\Program Files\GitHub CLI`).
- The pytest run shows a `StarletteDeprecationWarning`: Starlette's TestClient wants `httpx2` instead of `httpx`. Swapping `httpx==0.28.1` for `httpx2` was blocked by a local permission rule this session. Redo it once allowed.
- `next build` downloads Google Fonts (Inter, Geist), so it needs network access. `pnpm check` doesn't build.
