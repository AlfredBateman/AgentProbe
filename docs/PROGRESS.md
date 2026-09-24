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
- 2026-09-24 **B1.1: suite YAML schema; B2.1/B2.2: agents and suites CRUD** ([ADR 0010](decisions/0010-suite-schema-and-agent-config.md)):
  - `packages/core`: a new `agentprobe_core.suite` package.
    - `judges.py`: all 10 rule-based judges + `llm_rubric` + `consistency` as a `Field(discriminator="judge")` union, `extra="forbid"`. Implementations still come later.
    - `attacks.py`: an extension-point registry (`register_attack`/`is_registered_attack`); `prompt_injection.direct` and `tool_misuse` are pre-registered placeholders for Prompt 12.
    - `schema.py`: `Suite`/`Case`/`StatisticsConfig` (ADR 0006's `statistics:` block, all four fields configurable with the ADR's defaults). Limits: 256 KB, 500 cases, `runs_per_case` 1–20, 8,000-char input, unique case ids.
    - `parser.py`: safe YAML only (`yaml.safe_load`); anchors/aliases are rejected by scanning tokens before parsing (no billion-laughs). Errors read like linter output — line/column for YAML syntax, field path for schema violations. `suite_json_schema()` exports `Suite.model_json_schema()` for the web editor.
    - `suites/examples/support-agent-safety.yaml` (the SPEC.md §4.1 example) parses.
  - `apps/api`:
    - `agents.py`: CRUD at `POST/GET /projects/{id}/agents`, `GET/PUT/DELETE /agents/{id}`. Config is a discriminated union (`http`/`mcp`/`python`) validated per adapter_type; `python` is rejected (CLI-only). `auth_header` is JSON-encoded and encrypted into `secrets` via the existing `SecretBox`; responses only ever carry `has_secret`.
    - `suites.py`: `POST/GET /projects/{id}/suites`, `PUT /suites/{id}`, `POST /suites/validate`. A version bumps only when the uploaded YAML text differs from `yaml_source`; `test_cases` rows are synced per version and never mutated (old versions stay readable, per PLAN.md §2 #1).
    - `errors.py`: `ApiError` now carries optional `details`, so `_parse_or_422` can surface a suite's linter-style issue list in the standard error body.
    - `main.py`: `app.state.secret_box` is built once from `settings.encryption_key`; `apitest.make_settings()` now sets a default `encryption_key` so agent tests don't need to opt in.
    - `tests/test_idor.py`: `PROBES`/`SNAPSHOT`/`world` extended to cover every new agents/suites endpoint.
  - Tests: 42 new `packages/core` unit tests (schema limits, judge union, YAML safety, anchor bombs, the example suite); new `apps/api` integration tests for agents and suites (`test_agents.py`, `test_suites.py`). `pnpm check` and `pnpm verify` are both green (169 unit + integration tests total).

- 2026-09-24 **B1.2: LLM layer** (`packages/core/llm`, [ADR 0011](decisions/0011-llm-layer.md)):
  - `LLMClient` protocol (`complete(messages, role, json_schema=None, …)`, `embed(texts)`) and the `Client` that implements it over a `Provider`. Roles: agent, judge, attacker, summarizer, embedding. Models come from `config/llm.yaml`, overridable with `LLM_MODEL_<ROLE>`.
  - `mock` provider (default): deterministic; scriptable `Fixture`s (text or a whole `Completion`, e.g. a scripted safety block); a heuristic judge verdict (documented as not evidence of detection quality); 768-d fake embeddings whose cosine tracks text overlap.
  - `litellm` provider (Gemini), live only with `RUN_LIVE=1`. A LiteLLM extra `agentprobe-core[live]==1.102.1`, imported lazily, with no network at import.
  - Reliability:
    - per-model RPM window (waits);
    - per-model RPD persisted in `.agentprobe/llm-quota.json` on the Pacific day (fails with `QuotaExhausted`);
    - full-jitter backoff honoring Retry-After / Gemini `retryDelay`;
    - max concurrency;
    - per-run budget (calls, tokens, estimated USD) and a per-day USD cap.
  - Safety blocks come back as `Completion(blocked=True)`. Disk cache via `LLM_CACHE=1` (hits skip quota and budget). Pricing lives in `config/pricing.yaml`; a live client refuses to start if any configured model has no price. `EMBEDDING_DIM` is verified at startup.
  - `scripts/smoke_gemini.py`: one completion and one embedding. Run on the dev machine on 2026-09-24:
    - `gemini-3.5-flash-lite`: 1344 ms, 27/36 tokens, valid JSON verdict;
    - `gemini-embedding-2`: 914 ms, dimension 768.
  - Tests: 56 offline unit tests (limiter/backoff on a fake clock, budget, cache, mock determinism, safety blocks, error classification with fake LiteLLM callables, config), plus one `live` test (passed with `RUN_LIVE=1`).

- 2026-09-24 **B1.3: demo agents** (`demo-agents`):
  - One FastAPI app (`agentprobe_demo_agents.main:create_app`), one process, one port (`DEMO_AGENTS_PORT`, default 9000): `uv run python -m agentprobe_demo_agents` or the `agentprobe-demo-agents` console script.
  - Routes: `/support/v1` and `/support/v2` (identical code, different prompt files under `demo-agents/prompts/`), `/rag` (keyword retrieval over a small corpus, nested `result`/`meta` response shape — deliberately different from the others), `/vulnerable` (same engine as support, every safeguard off). `GET /health`.
  - `AGENT_MODE=mock` (default): a single rule-based `run_support()` in `engine.py`, parameterized by `SupportConfig` (`enforce_admin`, `leak_on_injection`, `leak_api_key`, `allow_drift`, `apply_flaky`) — v1/v2/vulnerable share the same code path, so the planted flaws are config, not a forked implementation. `AGENT_MODE=llm` routes through `agentprobe_core.llm.create_client()` instead (mock provider by default; `RUN_LIVE=1` for a live model), so it goes through the same budget guard as everything else.
  - The support bots derive `refund_window_days` from their prompt file's text via regex (`prompts.py`), re-read on every request (no caching) — editing the prompt file changes behavior immediately, including while the process is running (v2's prompt widens 30 days to 45, the planted regression).
  - Canary markers (`AP-CANARY-SYSPROMPT…`, `AP-CANARY-APIKEY…`, `AP-CANARY-RAGINJECT…`) follow `CANARY-[A-Z0-9]{4,}` so they also match `agentprobe_core.llm.mock.CANARY_PATTERN`.
  - Seeded flakiness (`flaky.py`): order lookups on `/support/*` fail at `FLAKY_RATE` (default 0.2) using a `random.Random(FLAKY_SEED)` that tests reset for exact, reproducible sequences.
  - `demo-agents/vulnerabilities.json`: a manifest of all 7 planted flaws (id, route, category, description, trigger, `suite_case_ids: []` — filled in once suites exist).
  - `demo-agents/README.md`: the "deliberately vulnerable; fake data only" warning, route table, `AGENT_MODE`/flakiness docs.
  - Tests (20, `pnpm check`): each planted flaw triggers (leak, injection, unauthorized delete, API-key leak, drift, RAG indirect injection via `context`), the v1/v2 refund regression, live prompt-file editing changes behavior, and flakiness is seeded/resettable. `pyproject.toml` per-file-ignores extended for `demo-agents/src/**` (fake secrets, seeded RNG — same reasoning as the existing `tests/**` ignore).

## Next
- B1.4: HTTP adapter (request template, dotted-path response mapping, timeouts, retries/backoff, SSRF guard) against these demo agents.

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
- Suite schema field names (judge params, `attack`/`attack_params`, `context` not `fixtures`), the attack registry's extension-point shape, anchor/alias rejection by token-scanning, and agent config validation living in `apps/api` (not `packages/core`, since the HTTP adapter itself is B1.4) ([ADR 0010](decisions/0010-suite-schema-and-agent-config.md)).
- LLM layer: roles spread across models for per-model free-tier quotas, RPD persisted and fail-fast, one retry policy (LiteLLM retries off), USD estimates from dated paid-tier prices, LiteLLM as a lazy opt-in extra; `LLM_MODEL_DEMO_AGENT`/`LLM_MODEL_MUTATOR` renamed to `LLM_MODEL_AGENT`/`LLM_MODEL_ATTACKER` ([ADR 0011](decisions/0011-llm-layer.md)).

## Known issues
- `pnpm verify` needs `TEST_DATABASE_URL`, `DATABASE_URL` and `ALLOW_DB_TESTS=1` (loaded from `.env`). Without them it refuses with exit code 2, which is intended. It takes about 2.5 min against Neon from here: each request costs 2–4 round trips of 80–140 ms (more on a bad network day). A Neon region closer to the developer would cut this proportionally.
- On native Windows, psycopg async needs `SelectorEventLoop`. Tests use the root conftest hook; `pnpm dev:api` passes `--loop asyncio:SelectorEventLoop`. Production start commands on Windows would need the same flag (Linux doesn't).
- Deploy (F4) must set `FORWARDED_ALLOW_IPS` to the proxy and keep the API reachable only through it. Otherwise the per-IP auth limit is either global (every user shares the proxy's IP) or spoofable (ADR 0009 §9).
- `JWT_TTL_MINUTES` now defaults to 15. A local `.env` that still says 60 keeps 60-minute access cookies.
- `uv` and `gh` are installed but not on PATH in some shells (`%USERPROFILE%\.local\bin`, `C:\Program Files\GitHub CLI`).
- The pytest run shows a `StarletteDeprecationWarning`: Starlette's TestClient wants `httpx2` instead of `httpx`. Swapping `httpx==0.28.1` for `httpx2` was blocked by a local permission rule this session. Redo it once allowed.
- `next build` downloads Google Fonts (Inter, Geist), so it needs network access. `pnpm check` doesn't build.
- Replacing or clearing an agent's `auth_header` orphans the old `secrets` row instead of deleting it (`ponytail:` comment in `agents.py`). Harmless (it's ciphertext, never returned) but worth a cleanup pass if the table's size ever matters.
- This machine has a stale machine-level `CURL_CA_BUNDLE=C:\Program Files\PostgreSQL\18\ssl\certs\ca-bundle.crt` (the file doesn't exist; left by an uninstalled PostgreSQL). The live LLM provider refuses to start while it is set. Remove it from an admin PowerShell: `[Environment]::SetEnvironmentVariable('CURL_CA_BUNDLE', $null, 'Machine')`, then open a new terminal.
- LiteLLM 1.102.1 ships a `cl100k_base` tokenizer file that fails tiktoken's hash check, so the first live import downloads the canonical file (hash-verified) into `.agentprobe/tiktoken/`. It needs network once; after that imports are offline.
- The daily quota file (`.agentprobe/llm-quota.json`) has no cross-process lock: concurrent processes can undercount by a few requests. Move the counters to Redis/Postgres with the multi-worker runner (B2.3).
- Free-tier RPM/RPD defaults (10/250) are placeholders: Google only shows the real per-model values in AI Studio. Set `LLM_RPM`/`LLM_RPD` in `.env` from https://aistudio.google.com/rate-limit.
