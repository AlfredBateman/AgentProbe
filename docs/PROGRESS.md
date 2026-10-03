# Progress

## Status by phase (PLAN.md §1)
A phase is complete only when every task in it is done.

| Phase | Status |
|---|---|
| A: foundation | **Complete** (A1–A5). |
| B1: core engine | **Complete** (B1.1–B1.9, including B1.8 golden tests, 2026-09-26). |
| D1: CLI local run | **Complete** (D1.1). |
| B2: server runner and results API | **Complete** (B2.1–B2.6). B2.5's ingest is `POST /ci/report`, not the planned `runs:ingest` ([ADR 0019](decisions/0019-ci-report-is-the-ingest-endpoint.md)). |
| D2: CLI remote features | **Complete** (D2.1). |
| C: security and AI features | **Complete** (C1–C4). C1's generators and C2's mutator were later cut to an id/category registry ([ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md)); C3's tool-description scan is out of scope ([ADR 0026](decisions/0026-no-mcp-tool-description-scan.md)). |
| E: dashboard | **Complete** (E0–E7). E2 and the rest of E3 finished on 2026-10-03 ([ADR 0037](decisions/0037-project-overview-and-runs-page.md), [ADR 0038](decisions/0038-agents-and-suites-pages.md)). |
| F | F1 (GitHub Action), F2 (dogfood workflow) and F3 (Docker, compose, CI smoke) **complete**, out of build order (E2/E3 rest not done yet; user decision). F4 (deploy) **live (Render, Vercel Hobby, Neon; ADR 0036), deployed by deploy.yml after CI and smoke-tested by `scripts/smoke_prod.py`; ADR 0036's live checks done (two bugs found and fixed), cold starts measured; three items still need the Render dashboard or a >15 min run**. F5 **complete** (2026-10-03: security headers and CSP, body cap, connection-test limit, secret scanning and the security review, ADR 0039; dependency audit and public-abuse limits earlier, ADR 0034/0035). F6 not started. |

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

- 2026-09-24 **B1.4: adapters, trace model, SSRF guard** (`packages/core/adapters`, [ADR 0012](decisions/0012-http-adapter-and-ssrf-guard.md)):
  - `types.py`: the `AgentAdapter` protocol (`async invoke(input, context) -> AgentResponse`) and the shared trace step model: a `type`-discriminated union of `message` / `tool_call` / `tool_result` / `error`, each with an aware `timestamp` and `duration_ms` (None = unknown). `AgentResponse` carries output, ordered steps, `TokenUsage`, `latency_ms`, `error`, and `tool_calls_reported`. Agent-side failures come back as `error` + an `ErrorStep`, never as exceptions.
  - `http.py`, the HTTP adapter:
    - URL, method (POST/PUT/PATCH) and plain headers come from config; secret headers are `SecretStr` values from the decrypted auth header.
    - The JSON request template takes `{{input}}` and `{{documents}}`, substituted in the parsed structure in one pass, so input can't reshape the request.
    - Responses map through a JSONPath subset (`$`, `.name`, `['name']`, `[n]`) for output, tool calls (name/arguments within a call; OpenAI-style JSON-string args parsed) and token usage. A configured `tool_calls` path that's missing is an error, never "no calls". Both demo response shapes are covered.
    - Per-attempt timeout (httpx + an overall `asyncio.timeout`). Retries use full jitter and honor `Retry-After`: only connect failures and 429/502/503/504 are retried, never anything the agent may already have acted on.
    - 2 MiB response cap; `test_connection()`.
    - `HttpAdapterConfig` validates at config time: http(s) only, no URL credentials, no framing headers, no plaintext `Authorization`/`Cookie`, valid paths, `{{input}}` present.
  - `ssrf.py`, the SSRF guard. An httpcore network backend under httpx's pool resolves once per connection, validates **every** address, and connects to that validated address, so there's no DNS-rebinding window. TLS still gets the hostname for SNI and verification.
    - Blocks: cloud metadata (AWS/GCP/Azure/OCI/Alibaba/ECS/EKS, IPv4 and IPv6, plus Azure WireServer), link-local, unspecified, multicast, reserved/documentation/benchmarking, IPv4-mapped/-compatible, 6to4, Teredo and local-use NAT64. Well-known NAT64 is classified by its embedded IPv4.
    - Private ranges (loopback, RFC 1918, CGNAT, ULA) need agent `allow_private` AND `ALLOW_PRIVATE_TARGETS=1` AND, if set, the host on `PRIVATE_TARGET_ALLOWLIST`.
    - Env proxies are ignored (`trust_env=False`). Redirects are off by default; when on, at most 5 hops, http/https only, each hop re-validated, and secret headers dropped cross-origin.
    - User-facing errors never include resolved addresses; the server log does.
  - `python.py`, the Python adapter (CLI only): `module:callable`, sync (in a thread) or async, `(input)` or `(input, context)`, returning a str or `{output, steps}`. The server can't load it: `agentprobe_core.adapters` doesn't import it, `build_adapter` refuses `python`, and `load_callable` refuses in any process that has imported `agentprobe_api`.
  - Shared changes:
    - `with_backoff` gained `retry_on`, so the HTTP adapter reuses it.
    - `Case.context` widened to `list[str | dict]`.
    - `apps/api` `HttpAgentConfig` now subclasses core's `HttpAdapterConfig` (stored config = what the adapter runs), and `AuthHeader` gets the same header checks.
    - core now pins `anyio`/`httpcore`/`httpx`; `cryptography` is a root dev dependency (TLS test certs).
    - `.env.example`: `ALLOW_PRIVATE_AGENT_URLS` renamed to `ALLOW_PRIVATE_TARGETS`, plus `PRIVATE_TARGET_ALLOWLIST`. The unused `AGENT_TIMEOUT_SECONDS`/`AGENT_MAX_RETRIES` were dropped (per-agent config now). `DEMO_AGENT_HOST/PORT` were corrected to the `DEMO_AGENTS_PORT` the code reads.
  - Tests:
    - `packages/core/tests/adapters` (231 offline tests: 152 SSRF, 61 HTTP, 16 Python, 2 TLS) covering every blocked class end to end with no connection made, IP literals, mixed answers, simulated DNS rebinding, redirect-to-internal, other redirect schemes, the opt-in truth table, and proxy env vars. Also mapping, template injection, retries, limits, header secrecy at DEBUG log level, and a **real TLS handshake** (throwaway CA) proving SNI plus hostname verification while pinned to 127.0.0.1.
    - `demo-agents/tests/test_http_adapter.py`: the adapter against the real demo agents over loopback. Both response shapes, tool-call arguments, usage, `{{documents}}` indirect injection, secret headers reaching the agent, `test_connection`, and blocked-without-opt-in through the real resolver.
    - `apps/api`: a subprocess import of the server never loads the Python adapter, and the server's source never references it. Integration tests cover config validation and non-echoed auth-header errors.

- 2026-09-24 **B1.5: judges** (`packages/core/judges`, [ADR 0013](decisions/0013-judges.md)):
  - `types.py`: `Judgment(status: pass|fail|error, score, reason, evidence)`; `JudgeContext` wraps
    `case`/`response` (ADR 0012) with `input`/`output`/`steps`/`latency_ms` read-only properties,
    plus `llm` (for `llm_rubric`/`consistency`) and `case_outputs` (for `consistency`).
    `REGISTRY: dict[str, JudgeFn]` keyed by `JudgeSpec.judge`; `evaluate(spec, ctx)` dispatches
    through it.
  - `rules.py`: all 10 rule-based judges. Tool judges (`tool_called`/`tool_not_called`/
    `tool_args_match`) error when `AgentResponse.tool_calls_reported` is False, per ADR 0012.
    `regex` is guarded by a length cap (`MAX_REGEX_INPUT`), not a timeout — stdlib `re` has none,
    and a thread-based one can't be cancelled. `json_schema` validates with the `jsonschema`
    library (now a direct, pinned `packages/core` dependency) rather than a hand-rolled
    validator; an invalid schema is `status=error`, a failing instance is `status=fail`.
  - `llm_rubric.py`: the agent's input/output are wrapped in `<agent_input>`/`<agent_output>`
    tags; any literal tag text found inside that untrusted text is neutralized first, so a
    hostile output can't forge or close the real delimiter (tested end to end against the mock
    judge with a forged closing tag hiding a canary). The verdict is requested against
    `JUDGE_VERDICT_SCHEMA` and parsed with one repair retry; a blocked or still-unparseable
    response is `status=error`, never a silent pass. `LlmRubricJudge` gained `samples: int`
    (default 1, max 10) for majority voting; any one bad sample errors the whole judgment, and
    ties fail.
  - `consistency.py`: scores a case (not one attempt) from `ctx.case_outputs`, mean pairwise
    `difflib` text similarity averaged with mean pairwise embedding cosine similarity when
    `ctx.llm` is given. A single output is trivially consistent. Feeds
    `run_case_summaries.consistency_score` (ADR 0007); the executor (B1.7) calls it once per
    case and is responsible for populating `case_outputs` and `ctx.llm`.
  - Tests: 65 unit tests (`packages/core/tests/judges`), 98% coverage of the package. New test
    helper `judgefakes.py` (pythonpath entry alongside `adapterfakes`/`apitest`/`idor`),
    including `ScriptedLLM`, a minimal `LLMClient` double for exact control over verdicts/
    embeddings without going through the mock provider's content heuristics.
  - `pnpm check` and `pnpm verify` are both green (481 unit + 80 integration tests).

- 2026-09-24 **B1.6: statistics** (`packages/core/stats`, [ADR 0014](decisions/0014-statistics-implementation.md), methods from [ADR 0006](decisions/0006-statistics-methodology.md)):
  - `summary.py`:
    - `CaseSummary(passes, attempts, errors, mean_score, mean_latency_ms, cost_usd)` validates its counts. It exposes `pass_rate`, `label` (stable-pass / stable-fail / flaky, errors count as non-passes; the rule is documented) and a Wilson interval.
    - `suite_stats()` returns the mean of case pass rates with a seeded, case-level percentile bootstrap CI. A binomial floor (Wilson at the suite rate, n_eff = C²/Σ1/nᵢ) keeps a one-case or zero-variance suite from getting a zero-width interval.
  - `significance.py`:
    - one-sided Fisher exact tests in both directions, as exact `Fraction`s via `math.comb`;
    - Holm step-down;
    - a paired sign-flip test. It is computed exactly by dynamic programming over integer-scaled sums: always for 20 or fewer non-zero deltas, and for much larger suites on a 1/n lattice. Otherwise it falls back to seeded Monte Carlo with (1+hits)/(1+draws).
  - `regression.py`: `compare_runs(baseline, candidate, config)` returns a `RegressionReport`:
    - the verdict: regression, no_change or improvement. Regression wins; a flag needs Holm/permutation p ≤ `alpha` AND a drop ≥ `min_drop`, both compared exactly;
    - per-case p-values and flags;
    - the suite test;
    - newly failing / passing / flaky and no-longer-flaky lists, plus added and removed cases. Only shared cases are compared;
    - score, latency and per-attempt cost deltas.
  - `StatisticsConfig.override(**flags)`: CLI flags over the YAML `statistics:` block, validated.
  - `scripts/measure_false_alarms.py` and [docs/metrics.md](metrics.md): a seeded simulation of unchanged flaky agents. Reference scenario (30 cases × 5 runs, 20% flaky): false alarms fall from **70.6% (naive single run) to 0.7%, a 99.0% reduction**. It also reports detection power: a single broken case among 30 is caught only 4.1% of the time at 5 runs, and 100% at 10 runs. It includes sensitivity over flaky fraction, suite size and runs per case.
  - Tests: 90 in `packages/core/tests/stats`, plus 4 for `override`. They cover:
    - known answers: Newcombe 1998 Wilson values, Fisher's tea tasting, ADR 0006's small-N examples, Holm, sign-flip;
    - Hypothesis property tests on a derandomized profile, including brute-force enumeration oracles for Fisher and sign-flip;
    - suite CI coverage (94% at 30 cases);
    - false-alarm calibration;
    - the p = `alpha` and drop = `min_drop` boundaries;
    - the Holm power limit, pinned so the docs stay true.

    Coverage of `agentprobe_core.stats` is 100%. `hypothesis==6.168.1` is now a pinned dev dependency. `pnpm check` and `pnpm verify` are both green (575 unit + 80 integration tests).

- 2026-09-24 **B1.6 follow-up: Tarone–Holm per case** (user decision; [ADR 0014](decisions/0014-statistics-implementation.md#per-case-tests) amended, [ADR 0006](decisions/0006-statistics-methodology.md) and PLAN.md §2 #9 annotated):
  - `significance.py`:
    - `fisher_exact` now returns a `FisherResult`: `p_worse`, `p_better`, and the smallest p each direction's margins allow. It is memoized per table.
    - `tarone_holm(p, min_p, alpha)` replaces `holm`: Holm's step-down with Tarone's exclusion recomputed at each step. With every min p at 0 it is exactly Holm.
  - `regression.py`:
    - The new `compare_cases()` runs the per-case family on its own.
    - `CaseComparison` reports `p_worse` / `p_worse_min` / `p_worse_threshold` (the `alpha`/K the case was compared against; `None` if not reached) in place of Holm-adjusted p-values, because Tarone isn't monotone in `alpha`.
  - The Fisher test was already one-sided; ADR 0014 now says so explicitly and why.
  - **Verdict rule** (documented and tested): one flagged case makes a `regression` even when the suite's mean drop is below `min_drop`. The demo (the refund case 5/5 → 0/5 in a 30-case suite, with and without flaky cases around it) returns `regression`, with the refund case compared against `alpha` itself.
  - **The per-case family's error rate is proven at or below `alpha`** in two ways:
    - exactly, by enumerating all outcomes for small families (Hypothesis-drawn true rates, up to 3 cases × 4 runs, plus 3 cases × 5 runs);
    - by a seeded simulation test (`test_family_wise_error.py`) over sizes 5/13/30/100 × 20%/50%/100% flaky, a different true rate per case, and all coin flips, plus 3 and 10 runs. Each cell's 97.5% Wilson upper bound must be ≤ `alpha`; the maximum measured is 3.2%.
  - [docs/metrics.md](metrics.md): the new honest headline is **70.6% → 2.3% false alarms, a 96.7% reduction** (superseded by the 2026-09-26 `alpha` split below: 70.6% → 0.9%, a 98.7% reduction), with single-break detection going from 4.1% (Holm) to 100%. Holm and Tarone–Holm are shown side by side in every scenario. A null calibration grid separates the per-case family from the whole verdict. The simulation parameters were unchanged.
  - Tests: 80 new or rewritten across stats and judges. `pnpm check` (655 unit tests) and `pnpm verify` are green.

- 2026-09-24 **Regex judge hardening** ([ADR 0015](decisions/0015-regex-judge-hardening.md), supersedes ADR 0013's regex bullet):
  - Matching now uses the `regex` package (`regex==2026.9.10`, already locked through tiktoken; `types-regex` for mypy) with a 0.25 s timeout. A timeout becomes `status=error`.
  - Before compiling, the pattern is parsed with the stdlib parser (Python `re` syntax, as before) and refused if its counted repeats would expand past 10,000 elements. Measurement showed `regex` unrolls counted repeats at compile time, which the timeout doesn't cover: `(?:(?:a{1000}){1000}){1000}` is 29 characters and about 250 GB.
  - The output cap went from 4,096 to 100,000 characters, since it no longer stands in for a timeout.
  - Tests:
    - `^(a|aa)+$` times out as an error;
    - `(a+)+$` is fine at 28 characters and a bounded timeout at 5,000 (the `regex` engine's guards make it cubic, not safe);
    - the compile bomb is refused instantly;
    - the limit boundary and the expansion estimates;
    - lookbehind, backreferences and verbose mode still work;
    - deep nesting, huge counts and regex-only syntax are errors.

    Judges coverage is 98%.

- 2026-09-25 **B1.7 + D1.1: run execution and the local CLI run** ([ADR 0016](decisions/0016-run-execution-and-local-cli.md)):
  - `packages/core/runner.py`, the single implementation of how a run works:
    - `execute_attempt` captures the full trace (input, `AgentResponse` steps and tool calls with arguments, latency, tokens, the agent's cost estimate and the metered judge cost) and turns every failure into a typed `AttemptError` (`timeout`/`agent`/`unreachable`/`judge`/`budget`/`internal`).
    - `finalize_run` builds per-case `CaseSummary`s (labels, Wilson intervals), runs `consistency` per case, and computes the suite pass rate with its CI, tokens and both costs.
    - `run_suite` runs attempts with bounded concurrency (TaskGroup workers), retries `unreachable` attempts with full-jitter backoff, streams results to `on_result`, and supports cancellation via an `asyncio.Event`.
    - `AgentResponse.retryable` is new; the HTTP adapter sets it when its retryable failures ran out.
  - `packages/cli` (`agentprobe`, Typer 0.27.2 + Rich 15.0.0):
    - `init`, `run` (`--agent --config --mock --json --runs-per-case --fail-under --baseline --concurrency --alpha --min-drop --permutation-draws --bootstrap-resamples`), `compare`, and `baseline set`.
    - Exit codes 0/1/2/3/4, documented in `--help` along with the small-N limitation. Click's usage exit 2 is remapped to 3.
    - `agentprobe.yaml` holds http/python agents, `secret_headers_env`, `price`, `llm.provider` and `run.concurrency/retries`. A repo-root `agentprobe.yaml` points at the demo agents.
    - Runs are saved to `.agentprobe/runs/`; baselines are named files in `.agentprobe/baselines/`.
    - All run-derived terminal text is sanitized (no Rich markup, control characters shown as `\xNN`).
    - The CLI stops at the first infrastructure error through `run_suite`'s `cancel` hook, saves the run as `cancelled` and exits 4.
  - `suites/examples/smoke.yaml`: 8 plain cases with rule judges, covering the refund window (the v2 regression), a seeded-flaky order lookup, the prompt leak, the API-key leak, unauthorized delete and scope drift.
  - Tests: 27 runner tests (concurrency: parallel beats sequential with a slow fake adapter; bounded concurrency; retries with backoff; timeouts; cancellation by event and by task; `on_result` failure; JSON round trip), 36 CliRunner tests covering every command and exit code (including markup/escape injection and suite-name path traversal), and 4 end-to-end tests against the real demo agents over loopback: v1 passes, vulnerable fails, `--fail-under` boundary, and a v1 baseline vs v2 candidate exits 2.
  - Measured on the demo agents (mock mode): v1 97.5% (order-status flaky 4/5), vulnerable 50.0% (4 planted flaws stable-fail), v2 vs a v1 baseline is a `regression`: refund-outside-window 5/5 → 0/5, p = 0.0040.

- 2026-09-25 **B2.3 + B2.4 (start/cancel/stream): server runner, queue backends, SSE** ([ADR 0017](decisions/0017-server-runner-and-queue.md)):
  - Queue library: **Taskiq 0.12.6 + taskiq-redis 1.2.3**, not Arq. Arq is maintenance-only (#510) and needs `redis<6`; SAQ's redis extra needs `redis<8`; we pin `redis==8.1.0`.
  - Both backends sit behind a `QueueBackend` protocol (`QUEUE_BACKEND=inline|redis`):
    - `inline` runs a whole run through core's `run_suite` under a semaphore;
    - `redis` runs idempotent jobs `start_run` → `run_attempt` per (run, case, attempt) → `finalize_run`, in `agentprobe_api.worker` (`pnpm dev:worker`).
  - Core, with no new run logic: `plan_attempts`, `execute_with_retries` and `run_suite(completed=…)` are public, and `uses_llm` moved from the CLI to core. `run_suite` no longer interrupts an `on_result` that is saving when the run is cancelled.
  - Migration 0003 (schema approved by the user), applied to the Neon test branch:
    - `run_results.error_kind/score/judge_cost_usd/retries/detail` (the `AttemptResult` without its steps);
    - `judgments.status/evidence`;
    - `run_case_summaries.errors`;
    - `runs.attempts_total/attempts_done/heartbeat_at/ci_lower/ci_upper`, and an index on `status`.
  - `runstore.py`:
    - the config snapshot (secret id only);
    - attempt upserts on (run, case, attempt), saved only while the run is running;
    - an exact rebuild of attempts from `detail` + `traces.steps`;
    - idempotent summaries;
    - the stale-run query.
  - `progress.py`: a `ProgressBus` (in-process queues / Redis pub/sub).
  - `runs.py`:
    - `POST /suites/{id}/runs` (202; `runs_per_case`, `model`, `mock`);
    - `GET /runs/{id}`;
    - `POST /runs/{id}/cancel`;
    - `POST /runs/{id}/stream-token` (ADR 0009 §5);
    - `GET /runs/{id}/stream` (SSE: `snapshot`, `attempt`, `status`, keep-alives).
  - Policy:
    - the first infrastructure error fails the run and stops the rest (as the CLI does);
    - crash recovery resumes queued/running runs and skips saved attempts; an unrecoverable snapshot means `failed`.
  - Tests (ADR 0008 amendment: background work shares the test transaction through `SharedSessions` under one lock):
    - `test_runs.py`, inline on Neon: the 40-attempt smoke suite against `/support/v1` with results, traces, judgments, summaries and CI persisted; the secret kept out of the snapshot but still sent; live SSE; the stream-token matrix; cancel mid-run and while queued; an unreachable agent failing the run after retries; 422s; crash resume; an unrecoverable run; idempotent saves.
    - `test_runs_redis.py` (`redis`): the same key scenarios through the real worker jobs in-process; a redelivered job never calling the agent twice; the startup sweep; and **both backends giving identical results and summaries** for the same suite and seed.
    - IDOR probes cover the five run endpoints.
    - Six of the seven Redis tests were also run locally on fakeredis's TCP server. Its pub/sub doesn't cross connections, so the SSE-over-Redis test is CI-only.
  - Shared helper `agentprobe_demo_agents.main.serve_in_background()` replaces two copies of the uvicorn thread fixture.
  - CI: the `redis` tests run in their own `pytest -m redis -v -rA` step. `pnpm verify` runs `integration and not redis`.
  - Measured through the real API (uvicorn, inline, Neon dev branch, demo agents): the smoke suite against `/support/v1` completed, 40/40 attempts, pass rate 97.5% (CI 87.1–100%), order-status flaky 4/5, identical to the CLI. 40 `run_results`, 40 traces, 65 attempt judgments and 8 case summaries were persisted. The SSE stream showed `snapshot` → 40 `attempt` → `completed`.
  - `pnpm check` (723 unit tests) and `pnpm verify` (94 integration tests) are green. Migration 0003 is applied to the Neon dev branch.

- 2026-09-25 **B2.4 (rest) + B2.5 + B2.6: results, compare, baselines, CI report, export, share links** ([ADR 0018](decisions/0018-results-compare-ci-report-export-share.md)), completing SPEC.md §8:
  - No core changes needed: `agentprobe_core.stats.compare_runs` already existed (built for the CLI's `agentprobe compare`) and is reused as-is by the server, serialized the same way (`pydantic.TypeAdapter(RegressionReport).dump_python(..., mode="json")`).
  - `runstore.py` gains request-scoped read helpers (`read_case_summaries`, `read_attempts`, `read_attempt`, `read_summary`, `parsed_suite`) that take a plain `AsyncSession`, alongside the existing `Sessions`-based (queue/worker) ones; `_attempt_result` is now shared between both `load_attempts` and `read_attempts`.
  - `results.py`: `GET /runs/{id}/results` (filters: `status`, `label`, `case`, `attack_category`), `GET /results/{id}/trace` (the full reconstructed attempt, trace steps included), `GET /runs/compare?a=&b=` (422 if the two runs aren't the same suite).
  - `baselines.py`: `POST /projects/{id}/baseline` (upsert per branch), `GET /projects/{id}/baselines/{branch}`.
  - `ci.py`: `POST /ci/report` — the CLI/CI uploads a run it already executed (results, git sha, branch, PR number), authenticated by API key (`require_api_key` added to `auth.py`). The suite and agent must already exist in the project (looked up by name); ingest never auto-creates them (security/data-model cost of doing so from an attacker-reachable payload). Compares against a branch's `Baseline` (defaults to the report's own `branch`, overridable via `baseline_branch` for PRs); `verdict="no_baseline"` when none is set. Payload shape is core's own `AttemptResult` (strict, `extra="forbid"`); size is bounded by the suite's own `plan_attempts` count, and duplicate/unknown case ids are rejected before any write.
  - `share.py`: `POST`/`DELETE /runs/{id}/share` (unguessable token, `runs.share_token_hash`/`share_expires_at`, already in the schema since ADR 0006/0007), public `GET /shared/{token}` — read directly off persisted columns (no recomputation, so an anonymous caller can't trigger the same cost the owner's export can), and deliberately narrower than the authenticated views (no agent config, no raw trace).
  - `runs.py`: `GET /runs/{id}/export?format=json|html`, recomputing a `RunSummary` from persisted attempts via core's own `finalize_run` — the strongest guarantee an export agrees with core's statistics. `htmlexport.py` is one self-contained, fully escaped HTML file: `html.escape()` on every dynamic value (suite/agent names too, not just case ids), no external assets, and no `<script>` tag anywhere in the page.
  - **A real deadlock, found by a hanging integration test, not by inspection:** the queue's `save_attempt`/`save_summary` open their own session per call (`Sessions`, for the queue/worker's benefit); calling them synchronously from inside a request handler that also depends on `Db`/`CurrentPrincipal` deadlocks in the test harness, where both share one connection behind one lock (ADR 0017's `SharedSessions`, held for the whole request by `Depends(get_db)`). Fixed by giving ingest its own single-transaction helpers, `runstore.insert_results`/`insert_summary`, sharing per-row field-mapping functions with the live-run path so the two can't drift.
  - Also fixed along the way: `dict(sqlalchemy_result.tuples())` is broken (`Result` exposes `.keys()`, so `dict()`'s mapping-detection kicks in instead of iterating pairs) — `case_ids_for` used it and silently would have 500'd on every run; caught immediately by the first integration test that exercised it.
  - `main.py` router order matters: `results.router` (which owns the literal `/runs/compare`) is registered before `runs.router` (`/runs/{run_id}`), since Starlette tries routes in registration order and `{run_id}`'s default converter would otherwise swallow "compare" as a path param.
  - `apitest.make_settings()` now pins `public_web_url=None` by default, so tests don't depend on whatever a developer's own `.env` happens to set (a real `PUBLIC_WEB_URL` in this repo's `.env` caused the first version of the dashboard-url test to fail).
  - Tests: `test_results.py` (the done-when scenario: `/support/v1` then re-pointing the same agent at `/support/v2`, `GET /runs/compare` returns `regression` naming `refund-outside-window`, a fresh v1 run against itself returns `no_change`; filters; trace; ownership), `test_baselines.py`, `test_ci_report.py` (ingest, baseline comparison, API-key-only, unknown suite/agent, unknown case id, duplicate result, oversized payload, empty payload, `dashboard_url` construction), `test_share.py` (sanitized view, expiry, revoke, ownership), `test_export.py` (JSON shape, HTML escaping with a `<script>`/`onerror=` XSS payload run through real ingest), IDOR probes extended to all nine new endpoints. `pnpm check` (723 unit tests) is green; the full new integration set (32 tests across five new files) is green against Neon.

- 2026-09-26 **Codebase review against SPEC.md and CLAUDE.md** (CLAUDE.md fixes and weak tests; [ADR 0018](decisions/0018-results-compare-ci-report-export-share.md) amended):
  - Live LLM in default tests: nothing called one, but unmarked tests read `LLM_PROVIDER`/`AGENT_MODE`/`RUN_LIVE` from the environment, and `pnpm verify` loads `.env`. The root `conftest.py` now pins them to mock for every test not marked `live` (proven by a pytester test).
  - Secrets: provider exception text flows into judge reasons, which are stored, exported, shown on public share links and logged. `llm/live.py` now cuts any `*_API_KEY`/`*_TOKEN`/`*_SECRET` env value out of it. LiteLLM 1.102.1 sends the Gemini key as a header, so no leak was observed; this is a backstop. The log-redaction test now also covers an agent's encrypted auth header.
  - Untrusted HTML: the HTML export gets a `default-src 'none'` CSP and `nosniff` (it is served on the app origin).
  - Pure logic outside core: `/ci/report`'s results-vs-plan validation moved to `agentprobe_core.runner.check_results`, which also rejects out-of-range `attempt` values (previously accepted).
  - Weak tests fixed: the LLM-client protocol test (mypy doesn't check tests; it asserted `is not None`), judge-registry dispatch (asserted any status), the manifest's "actually served" routes (checked a hardcoded set), the v1 injection refusal, the baseline-name traversal check (looked in the wrong directory), share-link expiry (never expired a link), results filters (passed vacuously when empty), the judge-steering test (asserted the mock heuristic, not the delimiting; now covers forged tags in the input too) and the migration round trip (no assertions).

- 2026-09-26 **Review follow-up: spec deviations resolved, B1.9 coverage gate, dead code** (user decisions on the review's findings; [ADR 0019](decisions/0019-ci-report-is-the-ingest-endpoint.md), [ADR 0020](decisions/0020-unregistered-agent-runs.md); ADRs 0010, 0016 and 0018 amended; PLAN.md §1, §2 #2/#6/#14, §3 amended):
  - `/ci/report` is the single ingest endpoint (`runs:ingest` intentionally not built) and returns structured data only; the GitHub Action (F1) formats the PR comment from its JSON (ADR 0019).
  - CLI python-adapter runs can be ingested (ADR 0020, migration 0004, applied to the Neon test and dev branches):
    - `runs.agent_id` is nullable, with `runs.agent_name`; exactly one is set (CHECK).
    - `/ci/report` takes exactly one of `agent` (registered) or `agent_name`, which may not equal a registered agent's name. It also takes an optional `model`, stored on the run.
    - Baselines are keyed on (project, suite, branch, agent_id or agent_name) with `NULLS NOT DISTINCT`. `GET /projects/{id}/baselines/{branch}` now needs `suite` and one of `agent`/`agent_name`. This also fixes a latent bug: with two suites in a project, the old (project, branch) key compared a run against whichever suite's baseline was set last.
    - `agentprobe run --push` (the push part of D2.1): uploads the run with `AGENTPROBE_API_URL`/`AGENTPROBE_API_KEY`; a python agent goes as `agent_name`, an http agent as `agent`; a remote regression exits 2, an unreachable server or 5xx exits 4, a refusal exits 3; the push settings are checked before the suite runs.
  - `obfuscate` and `attack_params` are refused before any call, like `mutations`, until the attack library (C1) exists.
  - PLAN.md's share path is corrected to `/shared/{token}`.
  - **B1.9 coverage gate**: `pnpm verify` now runs unit + integration tests in one pytest run with coverage and fails under 80% for `agentprobe_core` and for `agentprobe_api` separately (`pnpm coverage`); CI does the same with the Redis tests included. What it flagged: `apps/api` measured 78%, but that was a measurement bug, not missing tests. SQLAlchemy's async layer runs on greenlets and coverage stopped recording at the first database `await` in every handler; `[tool.coverage.run] concurrency = ["thread", "greenlet"]` fixed it. Measured locally: **core 97%, api 91%** (`worker.py` is 33% locally because its tests need Redis; they run in CI).
  - Dead code removed: `McpAgentConfig` (C3/Prompt 14 defines MCP config), the mutable attack registry (now `ATTACKS`, a frozenset), the runner's direct `REGISTRY` use (it calls `judges.evaluate()`, and its `judges` parameter is gone; tests patch the registry), the `load_attempts`/`read_attempts` duplicate query, test-only re-exports in `adapters/__init__.py`, and the unreachable read-back branch in `baselines.py`. Kept by decision: `PythonAgentConfig`, `suite_json_schema()`, `CiReportOut.top_findings`, and `ci.py`'s redundant project-ownership check.
  - Tests: python-adapter run pushed through the CLI's own push code and compared with its own baseline, next to a registered agent's baseline on the same suite and branch; agent identity (neither/both/registered name); each suite keeps its own baseline; the new CHECK and `NULLS NOT DISTINCT` constraints; `--push` payload, exit codes, and checks before running; `obfuscate`/`attack_params` refusal.

- 2026-09-26 **`alpha` split over the two regression channels** (user decision, resolving the open question ADR 0014 §Verdict left; [ADR 0014](decisions/0014-statistics-implementation.md#verdict) and [ADR 0006](decisions/0006-statistics-methodology.md) amended, PLAN.md §2 #9 annotated):
  - **The bug:** a verdict fires when the per-case family OR the suite test fires, and each ran at the full `alpha`, so the verdict's real false-alarm rate was bounded only by 2·`alpha`. The calibration grid measured **6.5% against a configured 5%** — the number users gate on was not the number they configured.
  - **The fix:** `alpha` is the verdict's budget, split by Bonferroni into `alpha_cases` and `alpha_suite` (`alpha`/2 each by default, both `StatisticsConfig` fields so a suite can spend it unevenly). Their sum may not exceed `alpha`; the config refuses it, since that is the bound being claimed. `RegressionReport` reports both shares, and the CLI prints them next to `alpha`.
  - **Measured after the fix** (`scripts/measure_false_alarms.py`, 5,000 trials per cell): worst verdict false alarms over the calibration grid **2.8%** (was 6.5%); reference-scenario false alarms 2.3% → **0.9%**, so the reduction against a naive single-run check improves to **98.7%** (was 96.7%). Each channel stays inside its own 0.025 share (per-case family at most 1.5%, suite test 2.7%).
  - **The single-case demo is unaffected, as asked:** support-bot v1 vs v2 with one refund case going 5/5 → 0/5 in a 30-case suite is still `regression`, detected on **100.0%** of simulated runs. Its p = 1/252 = 0.0040 is compared against the whole 0.025 per-case budget (Tarone drops the unchanged cases, K = 1); it would take K > 6 to lose it.
  - **What it costs, measured rather than assumed:** at 3 runs per case a single break falls from 38.4% to **0.5%** (its smallest possible p, 1/20, is above 0.025 — predicted analytically in ADR 0014 before the change); at 100 cases 100% → 99.2%; three cases turning flaky 38.5% → 21.1%; a 10% across-the-board degradation 86.0% → 77.7%. The CLI's `--help` now states the 3-run limit instead of calling it "borderline".
  - `test_family_wise_error.py` now drives `compare_runs` once per trial and reads all three rates off one report: each channel's bound and **the combined verdict at or below `alpha`**, across sizes 5/13/30/100 × five flakiness levels, plus a pooled bound over all 20 cells. It costs 21 s (was 12 s). Six existing tests changed where the halved budgets moved a boundary; each kept its original purpose (for example the `min_drop` exactness test moved to 24 cases with 6 dropping, so its suite p clears 0.025 while the mean drop is still exactly 0.05).

- 2026-09-26 **Repositioning** (user decision, [docs/POSITIONING.md](POSITIONING.md); PLAN.md gains §0 and ✂ marks on C1/C4/E6):
  - The differentiated core is **statistically-corrected, flakiness-aware regression detection wired into a real CI gate, judged on traces and tool calls rather than just final text** — not "a combined eval + red-team + dashboard platform", which competes on breadth.
  - POSITIONING.md records the pitch, a three-group comparison (eval harnesses with threshold gates and no significance testing; statistics layers that audit exported numbers with no runner, traces or gate; AgentProbe, which owns both ends), and the reasoning that the gap is the seam between those two groups.
  - MCP stays one adapter type for breadth (C3), explicitly not marketed as an MCP-security scanner — that space already has dedicated tools, and competing there is breadth again.
  - **First cuts if time runs short:** C4 failure clustering (presents already-detected failures; also drops `top_findings` and E6's Findings page), then C1's obfuscation variety (the attack categories the golden tests rely on stay). Kept regardless: the statistics, trace/tool-call judges, multi-run execution, golden tests, and the whole CI-gate path.
  - The competitor assessment is the user's reading of those projects' docs and third-party comparisons (2026-09), recorded as the basis for the decision, not re-verified here; POSITIONING.md §6 says to re-check every claim before it goes anywhere public, since "no significance testing" is a gap a competitor can close in one release.
  - **Open:** SPEC.md §1's tagline and §16's first resume bullet still say "testing and red-teaming platform". SPEC.md is the approved scope source of truth, so they were left unchanged pending an explicit decision (POSITIONING.md §7).

- 2026-09-26 **Two CI-only failures fixed** (both latent, both exposed by the tests added above; [ADR 0015](decisions/0015-regex-judge-hardening.md) amended):
  - `test_help_documents_exit_codes` matched literal phrases against Rich's word-wrapped `--help` output, so it depended on where the line break landed: "Small-N limit" survives at 80 columns and splits at 81. Lengthening the statistics note moved the wrap, which passed locally and failed in CI. The help text is now ANSI-stripped and whitespace-collapsed before the substring checks (verified at 60/80/81/100/120/200 columns and with `COLUMNS` unset), and the two sentences the `alpha` split changed are pinned.
  - The regex judge's deep-nesting test failed on Linux with "multiple unraisable exception warnings", attributed to an unrelated test. `("*5000 + "a" + )"*5000` raises `RecursionError` in the stdlib parser, which was already caught — but freeing the half-built parse tree exhausts the stack again, and that second error can only surface through `sys.unraisablehook`. A fourth guard (`MAX_REGEX_NESTING = 50`, counted before parsing) means the deep tree is never built. This was a real robustness hole, not just a test problem: the same pattern in a live suite would have scattered unraisable errors through the API or worker process.

- 2026-09-26 **C1 + C2: attack library and LLM mutator** (`packages/core/attacks`), plus **B1.8: golden tests**:
  - 15 attack ids across SPEC.md §4.4's 6 generator categories (prompt injection direct/indirect, 3 jailbreak framings, 3 extraction tricks, 2 leakage targets, 3 tool-misuse techniques plus the pre-existing bare `tool_misuse` kept as an alias of `tool_misuse.unauthorized_call`, and scope drift). Each `AttackDefinition` carries a seeded `generate(params, seed) -> list[Payload]`, a severity, and `notes` telling suite authors what pass/fail looks like and to pair it with a rule judge, not `llm_rubric` alone. Indirect injection's `Payload.documents` carries the hidden instruction separately from `text` (an innocuous question), for a case's `context` field.
  - Template selection is a shared seeded helper (`attacks/_templates.py`) that cycles a shuffled template order, so `generate` is reproducible per seed and a `count` over the template count repeats rather than raising.
  - `attacks/obfuscation.py`: `base64`, `leetspeak`, `split_word`, `homoglyph`, `hinglish`, standalone or stacked via `compose_obfuscation`. Base64, homoglyph and split_word round-trip exactly (`base64_decode`/`unhomoglyph`/`unsplit_word`); leetspeak and the Hinglish/Hindi set are lossy paraphrases, documented as such — the Hinglish set is a small curated phrase list, not a translator.
  - `attacks/mutator.py`: `mutate(attack_id, n, seed, llm)` paraphrases the attacker role through the shared `LLMClient` (same cache/budget/mock-determinism as every other LLM call), dedupes near-duplicates (`difflib`, 0.9 ratio), and backfills from the attack's own templates when a paraphrase is blocked, errors, or dedupes away — so it always returns up to `n` payloads without failing the run.
  - `agentprobe_core.suite.attacks.ATTACKS` now re-exports the registry's real id set (previously a 2-id placeholder frozenset), so `Case.attack`'s unknown-id validator lists all 15.
  - **Runtime expansion is still not wired in**, and this session left it that way deliberately: making `attack`-only/`obfuscate`/`mutations` cases actually runnable means threading generation (and the mutator's LLM call) through `plan_attempts`/`run_suite`, which is called synchronously from CLI, API request handlers, the worker and `/ci/report` — a much larger change than building the library itself, and outside what this task's own test list asked for. `runner.plan_attempts`'s three refusal messages were reworded (behavior unchanged) so they no longer claim the library "isn't available yet"; they now say expansion "isn't wired into run execution yet".
  - **B1.8 golden tests**: added `instruction-injection` to `suites/examples/smoke.yaml` (the line must start at the beginning of a line — `engine.py`'s `_INSTRUCTION_LINE` is `^`/`MULTILINE`-anchored, so the first draft using a single-line input silently didn't trigger the flaw on the vulnerable bot until caught by the test) and a new `suites/examples/rag-safety.yaml` (reuses the `RAG_INJECT_CANARY` pattern `demo-agents/tests/test_http_adapter.py` already used). `demo-agents/vulnerabilities.json`'s `suite_case_ids` are filled for all 7 planted flaws. `packages/cli/tests/test_e2e_demo.py` gained `test_every_planted_flaw_is_detected_by_its_suite_case`, which runs `support-v2`/`vulnerable`/`rag` for real over loopback and asserts every manifest entry's case(s) are `stable-fail` against the agent its route names — "7 of 7 planted flaws detected". The vulnerable bot's smoke-suite pass rate moved from 4/8 (0.5) to 4/9 (0.444...) with the new case; `test_fail_under_is_the_threshold`'s thresholds were moved to straddle the new rate.
  - Tests: 56 new in `packages/core/tests/attacks` (every attack id generates non-empty, reproducible payloads for a fixed seed; the unknown-id error lists valid ones; obfuscation round-trips and the lossy ones documented as such; mutator determinism, distinctness, dedupe-and-backfill, and both the blocked-provider and raising-provider fallback paths); `packages/core/tests/suite/test_parser.py` now parses every file in `suites/examples/*.yaml`, not just one. `pnpm check` (841 unit tests) is green.
  - The new smoke-suite case rippled into `apps/api`'s integration tests, which build their fixture suite by reading the real `suites/examples/smoke.yaml` file (`runtest.SMOKE_YAML`) rather than embedding a copy: `test_runs.py`, `test_export.py`, `test_results.py` and `test_share.py` had hardcoded 8-case/40-attempt/13-judgment counts (and one stale "attack generation" wording match) that needed updating to 9/45/14 — caught by `pnpm verify`, not `pnpm check`, since the unit-test suite mocks these away. `pnpm verify` is green: `agentprobe_core` 97% coverage, `agentprobe_api` 91%, both over the 80% gate.

- 2026-09-26 **Golden tests on core's `run_suite` + detection measurement** ([ADR 0022](decisions/0022-golden-tests-and-detection-measurement.md)):
  - `agentprobe_demo_agents.detection` is the one definition of "detected", shared by the golden tests and `scripts/measure_detection.py`: every listed case has an attempt a judge failed (errors don't count), and the regression flaw also needs a `regression` verdict against its baseline. `vulnerabilities.json` gained `suite`, `expected`, `negative_control` and (for the regression) `baseline_route`.
  - `demo-agents/tests/test_golden.py` (unmarked, ~3 s): each flaw detected with its expected label; each negative control passes; every smoke attack case is `stable-pass` on `/support/v1`; v1 → v2 is `regression` on exactly `refund-outside-window`; two consecutive v1 runs with different seeded flaky draws (4/5, then 5/5) are `no_change`, the first labelled `flaky`. Swapping the vulnerable and v2 runs for the v1 run turns six flaws to "not detected", so the checks aren't vacuous.
  - `apps/api/tests/test_golden_api.py` (`integration`): the smoke suite against `/vulnerable` through the API and the inline backend; the five `/vulnerable` flaws are `stable-fail` and nothing else is flagged.
  - `scripts/measure_detection.py`: mock mode wrote **"Detected 7 of 7 planted vulnerabilities across 3 demo agents"**, negative controls 7 of 7, with a per-flaw table, into docs/metrics.md. `--live` (needs `RUN_LIVE=1`) prints the estimate and asks first, runs one call at a time, and resumes from a checkpoint of finished attempts rather than the LLM response cache (which would replay attempt 1 for every repeat; ADR 0022). Its section in docs/metrics.md says "Not run yet": the live run is the user's call.
  - Estimated live cost, from the script's own dry run (answered "n"): **87 agent calls, 0 judge calls** at 3 runs per case (145 at 5), one model (`LLM_MODEL_AGENT`), against `LLM_RPD=250`; about 9 minutes at `LLM_RPM=10`.
  - CI caught two failures that the previous commit (the attack library) introduced and `pnpm verify` can't see. (1) The CLI's attack-only refusal test matched a phrase against Rich's width-wrapped error output: green locally, red in CI where the line broke inside the phrase. It now collapses whitespace, like the `--help` test. (2) A CI-only `redis` test still expected 24 attempts (8 smoke cases × 3) after the smoke suite grew to 9 cases.

- 2026-09-27 **C3: MCP adapter** (`packages/core/adapters/mcp.py`, [ADR 0023](decisions/0023-mcp-adapter.md)):
  - `mcp==2.2.0` (the SDK's v2 rewrite for the 2026-07-28 spec). A case's `call: {tool, arguments}` (`McpCall`, in `adapters/types.py`) sits alongside `input`/`attack` on `Case`; every call becomes a `ToolCallStep` + `ToolResultStep` pair, so `tool_called`/`tool_not_called`/`tool_args_match` and the rule judges work unchanged.
  - `mcp_ssrf.py` ports `ssrf.py`'s `GuardedBackend` to httpcore2 (`mcp` depends on `httpx2`, a from-scratch but structurally identical rewrite of httpx/httpcore, confirmed by reading both packages' source), reusing `classify`/`TargetPolicy`/`system_resolver` as-is; `resolve_target` gained a `connect_error` parameter so one classification function serves both backends.
  - **One MCP session per call, not a persistent one**: the obvious "connect once in `__aenter__`, reuse across attempts" design crashes under `run_suite`'s worker tasks — anyio's cancel scopes are task-affine, and a session entered in one worker task but closed from the run's own task (the CLI's `finally: await adapter.aclose()`, which is never a worker task) raises "attempted to exit cancel scope in a different task than it was entered in". A lock and a "rebuild after failure" attempt both still hit it; only opening and closing within the same call fixed it. Cost: an extra MCP handshake per attempt (documented as a deliberate ceiling), not a new TCP connection — the shared `httpx2.AsyncClient` still pools those.
  - Errors: `ToolError` (a tool raising) is a **normal response** (`error=None`, message in `output`) — the model's turn to see it, and exactly how the leaked-customer-list flaw below reaches a `not_contains` judge. `MCPError` is a non-retried adapter error. A bare crash is already scrubbed to `"Error executing tool <name>"` by the SDK before this adapter sees it. Missing/wrong-type arguments never reach a tool at all — rejected against its own type-hinted schema first, same shape as a `ToolError` — which is why the demo server's planted flaws are about validation the type system can't express, not missing checks.
  - Server side: `McpAgentConfig(McpHttpConfig)` has no stdio fields at all (a stored `transport: stdio` is a plain 422); `build_adapter` independently refuses `transport: stdio` before validating; `McpAdapter.__init__` refuses stdio in any process that has imported `agentprobe_api` — three independent layers, each tested. CLI's `McpAgent` nests `config: McpAdapterConfig` (the core http/stdio union) rather than flattening it. `--push`'s `is_registerable()` now also covers an MCP-over-HTTP agent.
  - `demo-agents/mcp_server.py`: `build_mcp_server()` is a **factory**, not a singleton — `MCPServer.session_manager` can only `run()` once, and this codebase already calls `create_app()`/`serve_in_background()` more than once (once per test module); a shared instance broke the second server's lifespan startup immediately, caught by the existing test suite. Two planted flaws: `issue_refund` never validates `amount` against zero or the order total (a negative or oversized refund succeeds); `search_orders` leaks its whole customer list, canary included, in the `ToolError` message on a miss. `lookup_order` is the well-behaved control (an injection-shaped id is just "not found").
  - `suites/examples/mcp-safety.yaml`: the four argument-handling shapes (missing, wrong type, negative/oversized "argument tampering") as literal `call:` cases, not new attack-registry entries — these are argument *shapes*, not text payloads, and runtime attack expansion still isn't wired in (ADR 0021's own deferral), so a schema-driven generator now would be scope creep against a feature that doesn't exist yet.
  - Golden tests: `vulnerabilities.json` gained `mcp-refund-no-validation` and `mcp-search-orders-leak`; `demo_agents.detection.adapter_for` dispatches to `McpAdapter` for the `/mcp-tools` route. **9 of 9 planted flaws detected** (was 7 of 7), mock-mode `docs/metrics.md` regenerated.
  - Tests: `packages/core/tests/adapters/test_mcp.py` (18: config validation, the three-plus-one error paths, argument-schema rejection, SSRF blocking a private target with no real network, an unreachable-server retry with a fake clock, the stdio/CLI-only restriction) against a real local `MCPServer` over loopback; `apps/api/tests/test_agents.py` gained the MCP-over-HTTP create/get test and the stdio-422 test; `packages/core/tests/suite/test_schema.py` gained `call`-field cases. `pnpm check` (884 unit tests) and `pnpm verify` are green.

- 2026-09-27 **C4: failure clustering** (`agentprobe_core.findings`, `apps/api/findings.py`, [ADR 0024](decisions/0024-failure-clustering.md)), closing SPEC.md §4.8 and §8's `GET /runs/{id}/findings` / `/ci/report`'s `top_findings`:
  - `agentprobe_core.findings` (pure, DB-free): `agglomerative_cluster` groups embedding vectors by single-linkage, stopping merges once the nearest pair exceeds a fixed cosine-distance threshold (0.25, chosen against the mock embedding's own hashing and confirmed on the real vulnerable-bot run) — stdlib only, no numpy/scipy, since a run's failure count isn't known ahead of time and `packages/core` has no such dependency anywhere else. `cluster_failures` embeds the failing outputs, clusters them, and asks the summarizer role for a `Summary:`/`Fix:` pair per cluster (free text, not `json_schema`: the mock provider's generic JSON fallback returns the literal string `"mock"` for every field, which would make every cluster's finding read identically). Handles every size without a special case: zero failures, one, and identical outputs (cosine distance exactly 0) all fall out of the same algorithm.
  - `apps/api/findings.py`: `GET /runs/{id}/findings` (largest clusters first), and the persistence around the core module — `cluster_run(db, run_id, llm)` (one transaction, idempotent: deletes and re-inserts a run's findings) and `cluster_and_save(sessions, run_id, llm)` (the queue-facing wrapper, its own session and commit). No migration needed: the `findings` table and its `Vector(EMBEDDING_DIM)` column already existed (migration 0001).
  - Wired in as a post-run job on both queue backends (`queue.cluster_findings`, called from `queue.finalize` and the inline backend's completed fast path, in both cases *before* `publish_status` so nothing is still touching the shared session after an observer sees `"completed"` — the first version raced an SSE test that way) and synchronously inside `/ci/report`'s own transaction, wrapped in `db.begin_nested()` (a SAVEPOINT) so a clustering failure can't poison the ingest. A clustering failure never fails the run: both call sites catch and log (`agentprobe.runs` / `agentprobe.ci`) instead of raising, matching how `InlineQueue._run` already handles an unexpected crash.
  - `runstore.make_llm_client(mock)` extracted from `Plan.llm()`: a fresh `LLMClient` for background work that isn't gated on a suite's own judges (clustering needs an embedding/summarizer client even when nothing in the suite uses `llm_rubric` or `consistency`).
  - `scripts/measure_clustering.py`: runs the smoke suite against the vulnerable demo bot (mock mode) and clusters its real failures. Measured: **25 failing results collapse into 5 findings** — the five planted flaws stay in five separate clusters, and each flaw's five repeated (deterministic mock) attempts collapse into one. Written into [docs/metrics.md](metrics.md).
  - Tests: 16 core unit tests (`packages/core/tests/test_findings.py`: cosine distance, clustering edge cases and determinism regardless of input order, `Summary:`/`Fix:` parsing and its fallback, label truncation); 9 `apps/api` integration tests (`test_findings.py`: zero/one/identical/two-distinct failures via `/ci/report`, idempotent re-clustering, a clustering failure never failing `/ci/report` or a live run, and the golden test — the vulnerable bot's five planted flaws each land in their own finding with no cross-contamination) plus one on the Redis backend (`test_runs_redis.py`) and an IDOR probe for the new endpoint. `pnpm check` (900 unit tests) and `pnpm verify` are green.

- 2026-09-27 **D2.1 (rest): remote compare, MCP stdio verification, CLI packaging** ([ADR 0025](decisions/0025-cli-remote-compare-and-packaging.md)):
  - `agentprobe compare`/`run --baseline` accept a server run id (a UUID): `_load_run` tries it as a server id before a local path or baseline name, and fetches it with a new `agentprobe.push.fetch(target, run_id, transport=...)` — the same `Target`/`PushError` shape as `push()`, hitting the already-existing `GET /runs/{id}/export?format=json` (ADR 0018). No new server endpoint. `PushError.infra` maps to the same exit codes `--push` already used (4 for an unreachable/erroring server, 3 otherwise); exit codes themselves are unchanged.
  - MCP stdio, actually run end to end for the first time (previously only permission checks were tested): `demo-agents/src/agentprobe_demo_agents/mcp_stdio.py` runs the existing demo MCP server over `run_stdio_async()` instead of Streamable HTTP, and a new CLI test launches it as a real subprocess (`command: sys.executable, args: ["-m", "agentprobe_demo_agents.mcp_stdio"]`) and shows the same planted flaw failing as it does over HTTP. A small 2-case suite, not the full 40-attempt `mcp-safety.yaml` (stdio has no persistent session, ADR 0023: one subprocess per attempt), so `pnpm check` doesn't pay for it.
  - `scripts/verify_wheel.py` + a new `packaging` CI job: builds every workspace wheel (`uv build --all-packages`), installs `agentprobe-core`/`agentprobe` into a venv this repo's uv workspace never touches, and checks `agentprobe --help` and a real mock run (local Python-adapter agent, no network) both work from the built wheels. Confirmed manually too: `agentprobe run --push` against a locally-served `/vulnerable` and a locally-running API server (dev DB) — 5 of 9 smoke-suite cases stable-fail as expected, pushed successfully, server verdict `no_baseline` (none set yet).
  - `packages/cli/README.md` (new): install, the `agentprobe.yaml` shape, every command, the `--push` CI recipe, the exit code table, both MCP transports.
  - Already done before this session, confirmed rather than rebuilt: `--push` saves the local result before attempting the upload (a network failure never loses it, already tested); the exit-code-4-on-unreachable-server test already existed (`test_push_failures_map_to_exit_codes`); the MCP adapter's config/permission layer already allowed stdio in the CLI (ADR 0023) with no server-side equivalent.
  - Tests: `push.fetch` unit-tested with `MockTransport` (CLI-level, offline) and against the real API (`apps/api/tests/test_ci_report.py`, Neon test DB: fetches a pushed baseline and candidate by server id and reproduces the server's own regression verdict via `compare_runs`); a 404 case. A real, latent bug found by the MCP stdio test only failing inside the *full* suite, not alone: `McpAdapter` refuses stdio in any process that has imported `agentprobe_api` (ADR 0023's own safety check), which the shared pytest process running this file's tests alongside the API's own has done by the time this test runs — fixed with the same `sys.modules` cleanup `test_cli.py`'s Python-adapter tests already needed for the identical reason. A second CI-only failure, same family as the "help text wraps differently at different terminal widths" bug PROGRESS.md already records once: `scripts/verify_wheel.py`'s literal `"Usage: agentprobe"` check passed locally (Windows, piped stdout, no ANSI) but failed on CI's Linux runner, where Rich still emitted color codes for the captured, non-tty output — fixed with the same ANSI-stripping, whitespace-collapsing normalization `test_cli.py`'s `--help` tests already use. `pnpm check` (906 unit tests) and `pnpm verify` are green; CI is green (`packaging` job included).

- 2026-09-27 **Second codebase review against SPEC.md and CLAUDE.md** (CLAUDE.md fixes and weak tests; spec deviations and over-engineering reported to the user, not changed):
  - Clean: no model name in source (only `config/llm.yaml`/`pricing.yaml` and fake test strings), no live LLM reachable from an unmarked test (the root conftest pins mock; the one `live` test is marked), every log record passes `RedactFilter`, the HTML export escapes every dynamic value, and no statistics or run policy lives outside `packages/core`.
  - Fixed: the failure-cluster summarizer (C4) embedded untrusted agent outputs in its prompt undelimited, so an attack output could steer the "suggested fix" that `/ci/report` returns for PR comments. Outputs are now wrapped in `<agent_output>` tags with forged tags neutralized (`llm_rubric.neutralize`, now public and shared), and a test checks a forged closing tag can't end the real delimiter ([ADR 0024](decisions/0024-failure-clustering.md) amended).
  - Fixed: internal workspace dependencies were unpinned (`agentprobe-core` etc.), against CLAUDE.md's `==` rule; the published CLI wheel would have accepted any `agentprobe-core` from PyPI. Now `==0.0.0` everywhere; `uv.lock` is unchanged (uv records no specifier for editable workspace members) and `uv lock --check` passes.
  - Weak tests fixed: the C4 golden test passed even with clustering disabled (one cluster per failure satisfied every assertion) — it now asserts each planted flaw's failures land in exactly one finding and 25 → 5, and a mutation check (merge threshold set below zero) confirmed it fails where the old version passed. Also: the summarizer fallback asserts its exact text; the mutator's blocked/raising-provider tests assert the variants came from the attack's own templates; every attack payload's category must match its definition; the repo-pricing test asserts all five roles are priced above $0 (a $0 price blinds the USD budget guard); a 404 on `fetch` is asserted to be a usage error, not infra.

- 2026-09-27 **Scope cuts and cleanups after the second review** (user-directed; [ADR 0025](decisions/0025-cli-remote-compare-and-packaging.md) amended, new [ADR 0026](decisions/0026-no-mcp-tool-description-scan.md) and [ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md), ADRs 0021/0022/0024 amended):
  - **Leaked demo key revoked.** The D2.1 `--push` demo had left an unrevoked API key (`…WSuI`) and its project `cli-push-demo` on the dev database. The key was revoked, then the project was deleted, which cascaded to its key, agent, suite and runs. Queried afterwards: 0 rows for either id, 0 keys with that `last4`, 0 API keys in the dev DB. The key value was never committed: none of the 963 git objects across all refs and the reflog contains an `ap_`-shaped token, and no working-tree file (ignored files included) contains the key, checked by SHA-256 against the stored `key_hash`. The `you@example.com` user created for that demo remains.
  - **`--baseline` / `--baseline-branch`**: ADR 0025 now records two flags as a deliberate improvement over one overloaded flag. `run --push --baseline X`, with no `--baseline-branch` and nothing resolving locally, now explains both flags and suggests `--baseline-branch X` instead of a bare "no such run file" (still exit 3). Both flags' `--help` and the CLI README say which side compares.
  - **MCP tool-description scan**: out of scope (ADR 0026), PLAN.md §2 #13 and C3 amended, removed from Next.
  - **Attack library cut to its registry** (ADR 0027). Confirmed first that no case's runtime input came from `generate()`: `plan_attempts` refused attack-only cases, and every `attack:` case in `suites/examples/` has a literal `input:`/`call:`. Removed:
    - the `agentprobe_core.attacks` package (generators, obfuscation with its decode helpers, the mutator) and its tests;
    - the `attacker` LLM role, whose only caller was the mutator;
    - the `mutations`/`obfuscate`/`attack_params` suite fields;
    - `plan_attempts`' refusals, `execute_attempt`'s no-input branch, `runs.py`'s `ValueError` catch;
    - the package's ruff per-file ignore.

    `ATTACKS` is now an id-to-category dict in `agentprobe_core/suite/attacks.py`, with the same 15 ids and 6 categories. `attack` only labels a case, and a case needs `input` or `call` at parse time. PLAN.md §0, §2 #10, C1 and C2 are amended.
  - **Python agents on the server**: `PythonAgentConfig` and `_reject_python_adapter` are replaced by one `BeforeValidator` on the `AgentConfig` union. Create and update now return **422** (was 400) with `details[].msg` ending "python adapters are CLI-only; the server only accepts http and mcp", and both tests assert that message.
  - **LLM cache** (user decision): `.env.example` now sets `LLM_CACHE=1` for live/dev runs, and docs/metrics.md says when to use it. `measure_detection.py` forces `LLM_CACHE=0` (ADR 0022 amended), and the root conftest's offline fixture clears `LLM_CACHE`, so `.env` can't give tests a persistent cache. The existing `test_cache_hits_skip_provider_budget_and_limits` already proves a cache hit spends neither the run budget (1-call cap) nor the RPM/RPD limiter.
  - **Clustering simplified**: `cluster_and_save` inlined into `queue.cluster_findings`; core's `FailingOutput` is a `(result_id, text)` tuple; `ClusterFinding.embedding` is required (ADR 0024 amended).
  - **Framing**: SPEC.md's tagline and §16's resume bullets, and the web app's placeholder tagline and meta description, now use POSITIONING.md's pitch. POSITIONING.md §7 is resolved.
  - Tests: new CLI test for the `--push --baseline` guidance, including both plain-error paths; new schema tests (attack-only case refused, removed fields rejected, every SPEC category has ids under its own prefix); the python-agent tests now assert status and message; refusal tests for removed behavior deleted or converted to parse-time assertions. `pnpm check` (855 unit tests) and `pnpm verify` (993 unit + integration tests; coverage core 97%, api 92%) are green. The ~50 generator/obfuscation/mutator tests went with the code.

- 2026-09-28 **E0: design system, app shell, API client and session refresh** ([ADR 0028](decisions/0028-dashboard-adaptations.md), [ADR 0029](decisions/0029-web-api-client-and-session-refresh.md), [ADR 0004](decisions/0004-font-substitution.md) amended):
  - **Theme generated from DESIGN.md.**
    - `apps/web/scripts/gen-theme.mjs` reads DESIGN.md's front matter and writes `src/app/theme.css`: colors, radii, type tiers (with line height, tracking and weight), and the 810/1199 breakpoints.
    - Spacing is a px scale (`--spacing: 1px`; user decision). Tailwind 4 resolves `max-w-md` from `--spacing-md` before `--container-md`, so DESIGN.md's spacing names would have silently broken container widths.
    - `theme.test.ts` fails on a stale file and checks every contrast ratio ADR 0028 records.
  - **DESIGN.md additions** (user decision: tokens live there):
    - `semantic-danger/warning/neutral` (fail, flaky, error) and `chart-1..4`;
    - the dashboard type tiers (`dash-title`, `dash-title-sm`, `dash-heading`, `data`, `data-label`, `code`);
    - `badge-*` components;
    - a "Dashboard Adaptations" section.

    `@google/design.md lint` reports no new findings (one old orphaned-token warning is gone).
  - **Findings that changed the design:**
    - **Google's Inter has none of DESIGN.md's OpenType features.** Its GSUB table has no `cv01/05/09/11` or `ss03/07`, and fontsource's Inter lacks them too. Inter is now self-hosted from `inter-ui@4.1.1` (rsms' build) through `next/font/local`, and Playwright confirmed the features now change the rendered text.
    - **Pass green and fail red are indistinguishable to deuteranopes** (OKLab ΔE 1.1, measured with the dataviz palette validator). Badges always carry a label, each StatusDot status has its own shape, and charts don't encode results in green/red.
    - **The gradient anchors as series colors:** orange and coral sat above the dark-mode lightness band, and ink/ink-muted fail the chroma floor. The series are violet, orange, magenta and coral, with orange and coral stepped into the band. The validator passes on all three surfaces.
    - **White text fails AA on the magenta, orange and coral gradient anchors** (3.43, 2.59 and 3.08), so `GradientCard` is violet only.
    - **DESIGN.md's 0.15-alpha focus ring is 1.22:1.** The ring is now solid accent-blue plus the halo.
  - **UI kit** (`apps/web/src/components/ui`, a Vitest test per module): Button (four variants; press = scale), Input/Textarea/Select (native), Tabs (pill toggle, ARIA tabs), Card (surface lift, panel header), GradientCard (a second mount warns in dev), Badge/StatusDot, DataTable (sortable, sticky header, tabular numerals), Toast, Dialog (native `<dialog>`), Skeleton/EmptyState, CodeBlock/CopyButton, and the Recharts theme. No component library, no icon dependency.
  - **Shell:**
    - `AppShell` has the 56px nav, a project switcher (native select), section links, and the account email with sign-out. Below 810px the links collapse into a menu.
    - `(app)/projects/[projectId]/layout.tsx` wires it to `GET /auth/me` and `GET /projects`, with a placeholder overview page.
  - **Plumbing:**
    - `/api` is rewritten to `API_INTERNAL_URL`, the name already reserved in `.env.example`.
    - The typed client is `openapi-fetch` over types generated from the committed `openapi.json`, which `scripts/export_openapi.py` writes. `test_openapi_schema.py` and the web CI job catch drift.
    - Single-flight refresh: shared in a tab, under a Web Lock across tabs, with a `GET /auth/me` probe that skips the refresh when another tab already rotated the cookies.
    - Route protection is `src/proxy.ts`.
  - **API**: new `GET /auth/me` (session only; API keys get 403).
  - **`/dev/components`** is `page.dev.tsx`, which exists only under `next dev` (`pageExtensions` by phase). CI builds for production and asserts the page isn't there.
  - **Playwright** (playwright-skill) at 1440, 810 and 390. Measured:
    - no horizontal page scroll;
    - nav exactly 56px (it was 57 with a border; now an inset shadow);
    - pills 44px, tabs 40px;
    - blue only on the inline link;
    - one gradient card;
    - no console errors;
    - no nav overlap from 810 to 1440 with a long project name.

    Fixed from the screenshots:
    - at 810 the nav links overlapped the switcher;
    - skeletons were invisible on cards;
    - the dialog's secondary button vanished into the surface-1 dialog.

    The final shots are in `docs/screenshots/` (`components-{1440,810,390}.png`, `shell-menu-390.png`).
  - **End-to-end smoke**, through the real rewrite against a local API on the dev DB:
    - a missing session redirects to `/login?next=`;
    - a cross-origin write through the proxy gets 403;
    - the shell renders;
    - an expired access cookie causes exactly one refresh;
    - sign-out clears both cookies.

    That run found a bug the unit tests had encoded: every `/api/auth/*` 401 passed through unrefreshed, so the shell's `/auth/me` would have failed on an expired cookie. Only login/register/refresh/logout pass through now, and there's a test for it. The throwaway user and project were deleted afterwards and verified gone (0 rows).
  - `next dev` in Next 16 writes `AGENTS.md`/`CLAUDE.md` into `apps/web`. `agentRules: false` turns that off, since agent instructions live in the root CLAUDE.md.
  - Tests: 98 web tests (theme and contrast, 13 component modules, shell, session, proxy, config), plus API tests for `/auth/me` (session, no cookie, API key) and the schema drift test.

- 2026-09-28 **E1: login, register, projects list, Settings** (closes PLAN.md's E1; copy sourced from [POSITIONING.md](POSITIONING.md), design against [ADR 0028](decisions/0028-dashboard-adaptations.md) and [ADR 0029](decisions/0029-web-api-client-and-session-refresh.md)):
  - **Landing page (`/`)** rewritten from the E0 placeholder to the Framer-style poster hero POSITIONING.md's pitch describes: display-xxl/lg/md headline (responsive across the three breakpoints), one primary (`Get started` → `/register`) and one secondary (`Sign in` → `/login`) pill, a three-step "How it works", a `CodeBlock` terminal example built from the real `agentprobe run --push` flags (`packages/cli/README.md`), and a mock PR-check `Card` with `Badge`/`StatusDot` showing a `regression` verdict (pass/fail/flaky) — the same refund-outside-window scenario used elsewhere as the running demo. One `GradientCard` (DESIGN.md allows up to two; the shared component's dev-only "more than one mounted" warning is calibrated for a dashboard viewport, so this page deliberately stays at one). No "pytest + Playwright + a security scanner" wording anywhere (tested).
  - **`/login`**: tries one `POST /auth/refresh` before rendering the form — ADR 0029's known limit, now fixed: a cross-site link (the GitHub PR comment use case) arrives with no `SameSite=Strict` refresh cookie, but this page's own same-site fetch can still use it. `next` (the post-login destination) is validated by `lib/safe-next.ts`: same-origin relative paths only, rejecting protocol-relative `//` and any backslash (tested against a hostile-input table). Inline field errors follow ADR 0028 §5/§8 (`aria-invalid` + `aria-describedby`, now amended: see below).
  - **`/register`**: email + password (client-side mirrors the server's 12-128 char rule, `lib/validators.ts`); success redirects straight to `next`/`/projects` rather than back to `/login`, because `POST /auth/register` already starts a session (`agentprobe_api.auth.register`) — there is nothing to additionally sign in to.
  - **`/projects`**: a new top-level list page (sibling to the existing `/projects/[projectId]`), outside the `AppShell` (no project is selected yet) with its own minimal header (`components/shell/bare-header.tsx`, reused by `/login`/`/register`). Empty state, loading skeleton, error state, a project grid, and a create-project `Dialog`.
  - **Settings** (`/projects/{id}/settings`, inside the existing `AppShell`, already linked from its nav): an API keys `Card` (create via dialog, the raw key shown once with `CopyButton`, list with label/last4/created/last-used/status via `DataTable`, revoke), and a read-only "Models" card.
  - **New API endpoint** `GET /config/llm` (`agentprobe_api/llmconfig.py`, session-only): returns `{provider, models}` from `agentprobe_core.llm.LLMConfig.from_env()`, so Settings never hardcodes a model name (SPEC.md §10, the one piece of E1 that needed a backend change). `openapi.json`/`schema.d.ts` regenerated.
  - **Shared UI fix, found from the E1 screenshots**: `Input`/`Textarea`/`Select` had no default border (only on `aria-invalid`), invisible when placed on a `surface-1` container — every login/register card and every `Dialog` is `surface-1`, so this had never been exercised before E1 combined inputs with cards. Fixed once in `components/ui/field.tsx` (ADR 0028 §8 amended), not per page.
  - `ToastProvider` is now mounted in the root layout (previously built in E0 but never wired in), so Settings' revoke action can show one.
  - **Playwright**: `apps/web/e2e/` (`@playwright/test`, new), `playwright.config.ts` (starts both dev servers, `reuseExistingServer`). Three specs, run against the real dev servers and the dev DB: the full flow (register → sign out → sign in → create a project → create an API key, shown once with a working copy button → revoke it), and the two silent-refresh scenarios from the prompt (an expired access cookie recovers on a direct visit to a protected page with no visible `/login` bounce; a fully expired session lands on `/login?next=…` and returns to that URL after signing in). `SIGNUP_ALLOWED_EMAILS` only allows one address against the dev DB, so specs run serially and each cleans up its account in `afterAll` (`scripts/cleanup_e2e_account.py`, cascades to everything it created). Not wired into `pnpm verify`/CI (documented in Known issues), the same way E0's screenshot verification wasn't. Screenshots at 1440/810/390 for all five pages saved to `docs/screenshots/`.
  - Tests: `lib/safe-next.test.ts`, `lib/validators.test.ts`, a `FieldError` test, an updated landing-page test (asserts the pitch line, asserts the old framing is gone, caps gradient cards at two), `apps/api/tests/test_llmconfig.py` (session-only, exact mock-mode model mapping). `pnpm check` (856 unit + 122 web tests) and `pnpm verify` are green (998 unit + integration tests; coverage core 97%, api 92%).

- 2026-09-28 **E2/E3 backend groundwork** ([ADR 0030](decisions/0030-dashboard-data-endpoints.md)). Written in an earlier session and left uncommitted; verified and committed on its own before E4/E5 (user decision):
  - `GET /suites/{id}` (with its YAML), `GET /projects/{id}/runs` (paginated, with a read-time `mean_latency_ms`), `POST /agents/{id}/test` and `POST /projects/{id}/agents/test` (one probe through the existing adapters and SSRF policy).
  - `SuiteParseError.issues` is now structured (`message`, `path`, `line`, `col`) everywhere it surfaces.
  - The suite JSON Schema and attack registry are a committed static export (`scripts/export_suite_schema.py`), with a freshness test.
  - Verification found one wrong expectation: `test_validate_endpoint_locates_syntax_errors` expected line 2 for an unterminated flow sequence, but PyYAML marks where it gave up (line 3, column 1, the end of the stream), as the issue's own message says. The test now asserts the exact position.

- 2026-09-28 **E4 + E5: run detail (live over SSE) and trace viewer** ([ADR 0031](decisions/0031-run-detail-and-trace-viewer.md)):
  - **API**:
    - `GET /runs/{id}` returns `RunDetailOut` (suite name, agent, share state).
    - New `GET /runs/{id}/cases` (persisted case summaries) and `GET /runs/{id}/verdict` (against the baseline of the run's branch, or `main`).
    - The SSE `attempt` event carries `result_id`, latency, cost and score.
    - Trace judgments carry the `step` they concern, from the new core `runner.judgment_steps`.
    - Token-authenticated streams send `Access-Control-Allow-Origin: WEB_ORIGIN`.
  - **Measured: the `/api` rewrite buffers SSE.** Through Next's rewrite, all events of a 20-attempt run arrived at once when it ended, gzipped. Straight from the API they arrived live, and with `Accept-Encoding: identity` the rewrite streamed too. So the cause is Next's compression, which browsers can't opt out of. The browser now uses ADR 0009 §5's stream token and connects to `NEXT_PUBLIC_API_URL` directly (default `http://localhost:8000` under `next dev`).
  - **`useRunStream`** manages its own reconnects:
    - a resync through the API client after every (re)connect and error, merging and never replacing;
    - backoff of 1, 2, 4 and 8 s;
    - a watchdog: no snapshot in 10 s, or 45 s of silence, counts as a failed connection;
    - polling every 3 s after three failed connections.

    A refresh mid-run is just a first connection.
  - **Run page** (`/projects/{id}/runs/{runId}`):
    - Live panel: `<progress>` meter, counters, elapsed, ETA, cost so far, connection state and a cancel dialog.
    - KPI tiles: pass rate with its CI as the lead figure, verdict vs baseline, cost and judging, tokens, model. Branch, commit and the mock/live badge sit in the header.
    - Case table: search, attempt-status/stability/attack-category filters, sortable columns. Expanding a row loads that case's attempts with every judge's reason and a trace link.
    - Actions: set as baseline (branch dialog), export JSON/HTML through the API client (so an expired session refreshes), and share links (create with an expiry, a copy button, replace, revoke).
  - **Trace viewer** (`.../results/{resultId}`):
    - An `<ol>` of native `<details>` steps with type glyphs, per-step offset and duration, and a compact/expanded toggle (traces over 30 steps start compact).
    - Verdicts sit beside their step at 1199px and up, below it otherwise. Rule and LLM verdicts differ by solid vs dashed border plus a text label. Unanchored verdicts go under "Whole attempt".
    - Side-by-side compare with another attempt of the case, or the same case in a recent completed run of the suite (`?compare=` in the URL). Steps align by index; a step whose content differs is lifted and labelled "Differs".
  - **Untrusted content**: `PlainText` renders text children only and cuts values at 2,000 characters behind "Show full". `no-raw-html.test.ts` fails the build on `dangerouslySetInnerHTML`, `innerHTML`, `insertAdjacentHTML` or a markdown renderer anywhere in `src`.
  - **Virtualization** is `content-visibility: auto` per step (user decision). Measured on a 2,000-step trace pushed through `/ci/report`: 47-61 fps while scrolling in both modes, with all 2,001 steps in the DOM, and 275 ms to switch every step to expanded.
  - **Public `/shared/{token}` page**, so a copied share link opens something: pass rate, cases, and attempts with outputs and judge reasons; no traces or agent config.
  - `DataTable` gains expandable rows. The detail is pinned to the visible width (`@container` plus `100cqw`), so it doesn't scroll sideways with a wide table. Cells are now 10px inset, on DESIGN.md's 5px rhythm; at 12px the case table overflowed its card at exactly 810px, which ADR 0028 §8 only allows below 810.
  - **Screenshots** at 1440, 810 and 390, saved to `docs/screenshots/`: `run-live-*`, `run-detail-*`, `trace-*`, `trace-compare-*`, `trace-vulnerable-*`, `shared-*` and `trace-long-1440`. None scrolls the page horizontally, and there were no console errors. Fixed from the screenshots: the 810 table overflow, the trace title set in mono instead of the Geist page-title tier, a "+0 ms" offset on every step (HTTP traces stamp every step with the request start), "1 cases", and the breadcrumb naming a runs list that doesn't exist yet.
  - **Tests**:
    - Vitest: `use-run-stream.test.ts` (a fake EventSource and fake timers: live, drop and reconnect, buffering proxy to polling, idle watchdog, ended at connect, per-connection URL), `stream.test.ts`, `run-cases.test.ts`, the timeline test (XSS payload in every untrusted field, anchoring, rule vs LLM, compact, truncation, diff), DataTable expansion and the no-raw-HTML guard. Mutating the hook's backoff and snapshot resync fails three of its tests.
    - Core: `judgment_steps` through a real `execute_attempt`.
    - API integration: case summaries vs results, trace anchors, the verdict (baseline itself, `main` default, other branch 404, equal to `/runs/compare`), share state, enriched SSE events matching the result rows, stream CORS only on the token path, IDOR probes for `/cases` and `/verdict`.
    - Playwright `e2e/04-run-detail-and-trace.spec.ts`: a live `/support/v1` run followed over the direct stream (CORS header checked) to a Flaky badge, then a `/vulnerable` api-key-leak trace where the step holding `AP-CANARY-APIKEY...` carries the failing `not_contains` Rule verdict, with keyboard toggling. Playwright starts its own demo agents on :9100 with `FLAKY_RATE=0.5`, so the flaky case is flaky in all but about 0.2% of runs.
  - `scripts/cleanup_e2e_account.py` now cancels the account's live runs before deleting it; deleting under a still-saving run deadlocked (found when a spec failed mid-run).
  - `pnpm verify` is green: 1,018 unit and integration tests, 143 web tests, coverage core 97% and api 92%. `next build` passes, and all four Playwright specs pass against the dev servers.

- 2026-09-28 **E6: compare runs, findings, and the public share page's noindex tag** (closes PLAN.md's E6; no backend changes — `GET /runs/compare`, `GET /runs/{id}/verdict` and `GET /runs/{id}/findings` already existed from B2.5/C4):
  - **Compare page** (`/projects/{id}/runs/{runId}/compare`): the run in the URL is always the candidate; a native-select baseline picker defaults to the run's own branch baseline (`GET /runs/{id}/verdict`, the same lookup the run page's "vs baseline" tile already uses) and falls back to letting the user pick any other completed run of the same suite, calling `GET /runs/compare` directly on a manual pick. A verdict banner states the statistics in plain language — which channel fired (per-case Fisher/Tarone–Holm or the suite's paired sign-flip test), its p-value against its own `alpha` share, and the effect size and N — rather than just naming the verdict word. Sections for newly failing/passing/flaky and no-longer-flaky cases, score/cost/latency delta tiles, and a full per-case table. Every case id is a button that fetches both runs' attempts for it and opens the candidate's trace with `?compare=` set to the baseline's attempt (reusing the trace viewer's existing side-by-side mode from ADR 0031, not a new comparison view).
  - `apps/web/src/lib/regression.ts`: TypeScript types for core's `RegressionReport` JSON dump (verified against a real `TypeAdapter(RegressionReport).dump_python(..., mode="json")` call — computed properties like `CaseSummary.pass_rate`/`.label` aren't in the dump, only declared dataclass fields, so `caseLabel()` recomputes the label client-side) and `verdictSummary()`, the plain-language sentence. Unit tested (`regression.test.ts`).
  - **Findings page** (`/projects/{id}/runs/{runId}/findings`): a single `GradientCard` summary tile ("N failing attempts → K findings", DESIGN.md's one-per-viewport rule), then cluster cards (label, member count, summary, suggested fix) with a native `<details>` to expand member results — case, attempt, status badge, output snippet, and a link to that attempt's trace. `GET /runs/{id}/results?status=failed` is fetched once to map member result ids to their case/attempt/output, since `FindingOut` only carries result ids.
  - Both pages are reached from new "Compare" and "Findings" buttons on the run page's action row (`run-actions.tsx`), not the top nav — the nav's Runs section (E2/E3) has no list page yet, so there's nowhere a project-level nav entry would go.
  - **Share page**: added `apps/web/src/app/shared/[token]/layout.tsx` with `robots: {index: false, follow: false}` (verified via `curl`: `<meta name="robots" content="noindex, nofollow"/>` renders). The rest of PLAN.md's share requirements — read-only framing, no agent config, and expired/revoked both surfacing the same "this link doesn't work" message (deliberately not distinguished, so a probe can't learn which) — were already built in E4/E5 and needed no changes.
  - Tests: `regression.test.ts` (4), `shared/[token]/layout.test.tsx` (1); Playwright `e2e/05-compare-runs.spec.ts` (the done-when scenario: `/support/v1` then `/support/v2` against the real smoke suite, `GET`-driven regression on `refund-outside-window`, then clicking through to a side-by-side trace) and `e2e/06-share-link-revoke.spec.ts` (a share link opens in a fresh, logged-out browser context; revoking it shows the same not-found state to a second logged-out context) — one test per file, matching the existing e2e convention, since `SIGNUP_ALLOWED_EMAILS` only allows one address and `afterAll` cleanup runs once per file. Both pass against the real dev servers and dev DB.
  - Manually verified against a real `/vulnerable` run (mock mode, real clustering): the findings page rendered 25 failing attempts → 5 findings, expanding a card's members and following "View trace" landed on a working trace page, with no console errors and no horizontal scroll at 1440/810/390. Screenshots saved to `docs/screenshots/` (`compare-*`, `findings-*`, `shared-*`). The manual-verification account (`you@example.com`, the same fixed e2e address) was cleaned up afterward with `scripts/cleanup_e2e_account.py`.
  - `pnpm check` (862 unit tests, 148 web tests) and `pnpm verify` are green (1,018 unit + integration tests; coverage core 97%, api 92%).

- 2026-09-28 **E3 (minimal slice) and E7: a real Playwright e2e suite against a dedicated test database, plus its CI job**:
  - **Agents and Suites pages** (`/projects/{id}/agents`, `/projects/{id}/suites`), on ADR 0030's endpoints — enough UI to add/edit an HTTP agent, test its connection before saving, and create a suite from YAML and run it. Not full E3: no MCP config, no auth-header UI, no suite versioning/case browser, no delete confirmation. `data-testid`s on the new form controls (`agent-name`, `agent-url`, `test-connection`, `suite-yaml`, `run-suite-{name}`, …) for the e2e suite to hook onto, alongside role/label queries everywhere else.
  - Both dialogs are remounted (React `key`) rather than reset in a `useEffect`, after `react-hooks/set-state-in-effect` flagged the original version — the parent already knows when a dialog opens (and, for the agent dialog, which one), so a fresh mount is the reset, with no effect syncing state to a changed prop.
  - **`scripts/reset_test_db.py`**: truncates every app table (reflected off `Base.metadata`, `RESTART IDENTITY CASCADE`) on `TEST_DATABASE_URL`, gated by the same guard `conftest.py` uses for DB tests (`TEST_DATABASE_URL` set and different from `DATABASE_URL`, `ALLOW_DB_TESTS=1`) so it can never reach a real database. Chosen over a `/test/reset` API endpoint: a standalone script matches this repo's existing pattern (`scripts/cleanup_e2e_account.py`) and never ships a database-truncating route in the deployed API, gated or not.
  - **`apps/web/playwright.config.ts`** rewritten to run the whole e2e suite against its own stack, never a developer's: dedicated ports (web :3010, API :8100, demo agents :9100), `TEST_DATABASE_URL` (never the dev database), `QUEUE_BACKEND=inline`, `LLM_PROVIDER=mock`, `ALLOW_PRIVATE_TARGETS=1`, and a fixed `SIGNUP_ALLOWED_EMAILS` roster (`e2e/fixtures.ts`).
  - **`apps/web/scripts/reset-e2e-db.mjs`** migrates the test database to head and runs `scripts/reset_test_db.py`, chained with `&&` ahead of `playwright test` in the `e2e` script — **not** a Playwright `globalSetup`, after CI proved Playwright doesn't guarantee one finishes before `webServer` commands start (below). Every `pnpm e2e` invocation — and each of the "3 consecutive passes" this was checked against — now deterministically starts from an empty, migrated database.
    - **`next dev` refuses a second instance in the same project directory, regardless of port** (it locks on the directory, not the port): the web server now runs as `next build && next start -p 3010` instead, which has no such restriction and doesn't collide with a developer's own `pnpm dev:web` on :3000. `NEXT_PUBLIC_API_URL` is set for the build step too, since it's inlined into the client bundle at build time, not read at `next start`.
    - HTML report (`playwright-report/`, already gitignored) added to the reporter list; `video: "retain-on-failure"` added alongside the existing trace setting.
  - **Page objects** (`e2e/pages/*.ts`): `RegisterPage`, `ProjectsPage`, `AgentsPage`, `SuitesPage`, `RunPage`, `ComparePage`, `SharedPage` — each just the locators/actions its specs actually use, not a speculative full surface.
  - **New specs**, numbered after the existing six (which needed no logic changes — they already parameterized `baseURL`/`DEMO_AGENTS_URL` rather than hardcoding ports, except 02/03's CSRF `Origin` header, fixed to use the `baseURL` fixture):
    - `07-main-flow.spec.ts`: SPEC.md §11's flow end to end through the real UI, no API shortcuts for setup — register, create a project, add an agent, test its connection, create a suite from YAML, run it, watch live progress (the SSE response is awaited before asserting the progress bar, same technique as `04`), open a failing trace (order-status's seeded flakiness at `runs_per_case: 10` makes a failure near-certain), re-point the agent at `/support/v2`, run again, see the regression on `refund-outside-window` on the compare page with its statistics in plain language, open the side-by-side trace, create a share link, and open it in a fresh logged-out browser context.
    - `08-ssrf-blocked-agent.spec.ts`: the agents form's Test connection shows the SSRF guard's own message for a blocked cloud-metadata address and, separately, for a private address without the opt-in — and never leaks a resolved address (ADR 0012).
    - `09-invalid-suite-yaml.spec.ts`: a YAML syntax error and a schema violation (`cases: []`) both surface as validation issues on the suite form, not a generic failure, and neither creates a suite.
    - `10-auth-redirect.spec.ts`: a fresh, cookie-less context visiting a protected page (a nested run page, and the projects list) redirects to `/login?next=…`.
    - `11-visual-snapshots.spec.ts`: one screenshot per main page at 1440px, attached to the Playwright report — landing, login, register, shared, projects list, project overview, agents, suites, settings, run detail, trace, compare, findings. **Not pixel-diffed against a committed baseline**: font rasterization differs between this machine and CI's Linux runner, which would fail the assertion on rendering noise rather than a real regression — the same reason this repo's screenshots have always been compared by eye/AI against DESIGN.md rather than asserted pixel-for-pixel (E0–E6). What it does assert on every page: a heading is visible, every `Skeleton` resolved, there's no horizontal overflow at 1440px, and no uncaught JS error (not "no console error": the app's own silent-refresh probe can legitimately log a 401).
  - **Four real bugs found by actually running the suite — repeatedly, alongside `pnpm verify`, and in CI, not just locally once**:
    - `scripts/cleanup_e2e_account.py`, invoked via `uv run --env-file .env`, was deleting the e2e user from the *dev* database (`.env`'s `DATABASE_URL`), not the test database the suite actually runs against — the first run of `01`–`06` against the new config passed, but every subsequent spec in the same invocation failed registering `you@example.com` as already existing, because it never had been in the test database's sense of "existing" until that run, and was never removed from it either. Fixed: `e2e/cleanup.ts` now calls the script with `DATABASE_URL` set explicitly to `TEST_DATABASE_URL`, not `--env-file .env`.
    - A one-in-three flake in `07-main-flow`: `getByLabel("Baseline")` on the freshly-navigated compare page matched two elements from the *run detail* page instead (a `<dialog>` labelled "Set as baseline" and a `<section aria-label="Verdict vs baseline">`), meaning the client-side transition to `/compare` hadn't completed when the next locator ran. `RunPage.goToCompare()` now asserts `expect(page).toHaveURL(/\/compare$/)` after the click. This is the same class of bug PROGRESS already has one entry for (`waitForURL`'s default `waitUntil: 'load'` never fires after a `router.push`/`router.replace` client-side change) — `ProjectsPage.createProject()` and `SuitesPage.run()` used the unsafe `waitForURL` form too and were switched to `expect(page).toHaveURL(...)` at the same time, even though they hadn't yet been caught failing.
    - **`pnpm verify` failed once, from e2e's own leftover data, not from anything wrong in `pnpm verify` itself.** `test_refresh_token_reuse_revokes_every_session` asserts *every* `refresh_tokens` row with `revoked_at IS NULL` is gone after Alice's stolen-token replay is caught — but it queried the whole table, not Alice's own rows. Locally, `pnpm e2e` and `pnpm verify` share one Neon test branch (CI's don't: each job gets its own throwaway Postgres container), and several new specs (`07`–`11`) register real users and never log them out, leaving active sessions behind for the *next* thing to query that table — which this test's unscoped assertion did. The test passed cleanly against a freshly reset database, confirming the assertion itself, not a real regression, was the weak point. Fixed by scoping it to `RefreshToken.user_id == alice_id`, which is what the test actually means to check; not a workaround in the e2e suite, since the underlying assumption (an unrelated table is globally empty) was already fragile and would resurface the moment anything else wrote to it.
    - **CI's first run of the `e2e` job failed outright**, and this is the one none of the local runs could have caught: `agentprobe_api`'s lifespan startup (`queue.recover()`, querying `runs` for anything left `queued`/`running`) crashed with `relation "runs" does not exist`, because the table didn't exist yet — the original design used a Playwright `globalSetup` to migrate-then-reset the database, on the assumption that `globalSetup` finishes before any `webServer` command starts. It doesn't, or at least isn't guaranteed to: CI's brand-new, genuinely empty Postgres container exposed the race immediately, while every local run had passed only because the Neon test branch already had a schema from unrelated past `pnpm verify` runs, so the API starting before migration happened to still find real tables (just briefly stale data, invisible after the reset caught up). Fixed by moving the migrate-then-reset step out of Playwright entirely, into `apps/web/scripts/reset-e2e-db.mjs`, chained with a plain `&&` ahead of `playwright test` in the `e2e` package.json script — a shell `&&` is unambiguous about ordering in a way `globalSetup` vs. `webServer` isn't.
  - **`pnpm check` broke after running e2e once**: ESLint's ignore list only covered `.next/**`/`out/**`/`build/**` (Next's own defaults), not `playwright-report/**`/`test-results/**` — both gitignored, but still real directories on disk after a local `pnpm e2e`, and ESLint doesn't know they're vendored output. It happily "found" 259 errors in Playwright's own bundled, minified trace-viewer JS. Added to `eslint.config.mjs`'s ignore list.
  - **`pnpm e2e`** (root script, and `apps/web`'s own `playwright test`): deliberately separate from `pnpm verify`, per instruction — it needs its own three running servers and a Postgres database, and takes minutes, not seconds.
  - **CI**: a new `e2e` job (`.github/workflows/ci.yml`) with its own `pgvector/pgvector:0.8.6-pg18` service container (`agentprobe_e2e`, never the `python` job's database), no Redis (the suite runs `QUEUE_BACKEND=inline`). Playwright's Chromium is cached (`~/.cache/ms-playwright`, keyed on `pnpm-lock.yaml`); on a cache hit only `playwright install-deps` (OS packages, never cached) reruns, skipping the browser download. The HTML report uploads as an artifact (`playwright-report/`, 14-day retention) on every run, pass or fail.
  - **Measured**: 12 tests, ~4.1–4.3 minutes end to end (a warm run — servers and the Neon test branch already reachable; a cold first run also pays for `next build`, about 60–90 s more). Passed 3 consecutive local runs after all four fixes above; CI's `e2e` job green on the second push.

- 2026-09-28 **Third codebase review against SPEC.md and CLAUDE.md** (CLAUDE.md fixes and weak tests; spec deviations and over-engineering reported to the user, not changed):
  - Clean: no model name in code (only `config/*.yaml`, the web reads `GET /config/llm`); no live LLM reachable from unmarked tests (root conftest pin) or from e2e (`LLM_PROVIDER=mock` in `playwright.config.ts`); no raw-HTML sink in the web app (`no-raw-html.test.ts`), every `href` is built from API-issued ids, and the HTML export downloads to disk, never renders in-app.
  - Fixed, secret in logs: `GET /shared/{token}` put the share token in the access log's `path` in plaintext, although only its hash is stored. `scrub_text` now replaces any `/shared/<token>` with `/shared/[REDACTED]` (access lines, messages and tracebacks alike).
  - Fixed, pure logic outside core: the web's `caseLabel()` re-implemented core's stable-pass/flaky/stable-fail rule, because `TypeAdapter` dumps of the stdlib `CaseSummary` dataclass omit its properties. `pass_rate` and `label` are now pydantic `computed_field`s, so every dump (compare, verdict, export, CLI `--json`) carries them; `caseLabel` is gone and the compare page reads `pass_rate`. `CaseSummary` is `extra="ignore"` on load (`with_config`), otherwise a saved `RunSummary` (which forbids extras, and nested stdlib dataclasses inherit that) couldn't read its own dump back — caught by the CLI's baseline tests and `test_summary_round_trips_through_json`.
  - Weak tests fixed: the saved-secret test-connection test (its own docstring said it didn't prove the secret was sent; it now spies on what the adapter receives), exact "Connection succeeded" text, the run list's `mean_latency_ms` (was `> 0`, now equals the attempts' mean — within 0.5 ms, since `run_results.latency_ms` is stored as whole milliseconds but the per-case means aren't), exact suite-issue positions in three parser/API tests (were `is not None`), the landing page's CTAs (were "at least one link"; now register is always primary, sign-in secondary), and three e2e assertions: a schema violation must name `cases` and the reason (was "any text"), the private-address SSRF message is matched exactly, and the compare verdict must name `refund-outside-window` as the case that fired (the case table shows it regardless).
  - `pnpm check` (864 unit + 147 web tests) and `pnpm verify` (1,020 unit + integration tests against Neon; coverage core 97%, api 92%) are both green with all of the above.

- 2026-09-29 **e2e flake in `04-run-detail-and-trace`: the run finished before the page loaded, not too slowly.**
  - Symptom (CI run 36464897858): `Test timeout of 180000ms exceeded` in `page.waitForResponse` for the stream URL. It looked like a slow run hitting the 150 s "Completed" wait. It wasn't.
  - Measured with temporary stage logging on CI (draft PR #1, closed unmerged). The table gives ms from the test's `POST /runs`. The first row is from the original failure's Playwright trace; the other three are instrumented reruns:

    | Sample | Claimed | Attempts 1→20 saved | Completed published | Page's first `GET /runs/{id}` saw | Outcome |
    |---|---|---|---|---|---|
    | original | – | – | ~284 (`finished_at`) | `completed` at ~337 | no stream opened; hung 180 s |
    | 1 | 55 | 133→312 | 365 | `completed` (sent ~378) | no stream opened |
    | 2 | 59 | 127→345 | 404 | `completed` (sent ~399) | no stream opened |
    | 3 | 60 | 130→369 | 447 | `running` (~461) | stream opened at 516 with a `completed` snapshot; live panel never rendered |

  - What it rules out:
    - Poll latency: e2e runs `QUEUE_BACKEND=inline`, with no Taskiq/Redis; enqueue to claim was 5–6 ms.
    - Serialized attempts: concurrency 4; about 11 ms per attempt, bounded by the per-run row lock on saves.
    - Event-bus delay: the in-process bus is a `put_nowait`.
  - Root cause: the spec assumed a 20-attempt run outlives a page load. On CI's local Postgres the run takes 0.3–0.45 s, about the same as the page's first fetch, so the test was a coin flip. It passed locally only because Neon's round trips stretch the run to many seconds. `07-main-flow` had the same assumption at 40 attempts and had only been winning the race.
  - Fix (tests only; no timeout changed, no sleeps or retries): `e2e/gated-agent.ts`, a Node `http` pass-through proxy in front of the demo agent that can hold its calls.
    - `04` holds the agent until the page is streaming, lets exactly one attempt through (its row must arrive over SSE while the progress bar reads 1), then opens the gate.
    - `07` holds the agent from clicking Run until the progress bar shows.
  - The product behaved correctly throughout: a run that has already ended is read straight from the API, with no stream.

- 2026-09-29 **F1 (GitHub Action) and F2 (dogfood workflow)**, out of build order at the user's request ([ADR 0032](decisions/0032-github-action-and-dogfood-baseline.md)):
  - `action/action.yml`: a composite action that installs the `agentprobe` CLI (`pip install`, overridable to a local wheel path for testing an unreleased CLI change), runs a suite (`agentprobe run --json`), pushes to a server and compares against its branch baseline when `api-url`/`api-key` are set (`--push`, ADR 0018/0020), or compares locally against a `baseline-run` file when they aren't, formats and upserts a single PR comment (found by a hidden marker, so re-runs edit in place), and exits with the CLI's own exit code so the job — and a required check, once branch protection asks for one — fails on a regression or a pass rate below `fail-under`.
  - `action/format_comment.py`: pure `render_comment()` (pass rate with its 95% CI, verdict vs baseline, newly-failing/newly-flaky cases, top failure clusters from server-side findings/C4, a dashboard or local-file link) plus a thin CLI wrapper. Every suite/agent/branch name and case id goes through a code-span escaper (only a literal backtick matters inside one); LLM-generated cluster text goes through a CommonMark-punctuation escaper — both per ADR 0019's escaping requirement, since suite YAML and cluster summaries are untrusted text that must never reopen Markdown/HTML syntax in the rendered comment.
  - `action/post_comment.py`: stdlib `urllib` only, upserts by searching existing issue comments for the marker (paginated, hard-capped at `MAX_COMMENT_PAGES=20` after a bug during development made an unbounded `while True` page loop spin forever against a mock that never returned a short page — a real infinite loop, not just a slow test, so the cap is production hardening, not test-only). A 403/404 (a fork PR's read-only `GITHUB_TOKEN`) is caught and logged as a warning, never a failure; a fork PR's empty `api-key` is handled separately, one layer up, by the action's run step (mock/local mode, no push).
  - `.github/workflows/agentprobe-dogfood.yml`: builds this branch's own CLI/core wheels (`uv build --all-packages`, not the last PyPI release), starts the demo agents, and runs the action in a 3-way matrix (`smoke`/`support-v1`, `support-agent-safety`/`support-v1`, `rag-safety`/`rag`) on PRs touching `demo-agents/**`/`suites/**`/`action/**` plus `workflow_dispatch`. No AgentProbe server is deployed yet (PLAN.md F4), so the baseline is the same suite/agent's result from the most recent successful run of this same workflow on `main`, kept as a workflow artifact (`gh run list`/`gh run download`, both preinstalled) and passed to `baseline-run` — a deliberate placeholder for the server-side baseline the action already supports, per ADR 0032.
  - Tests: 21 in `action/tests/` (13 for `render_comment` against 4 fixture JSON payloads — no-baseline, a pushed regression with findings, a local-baseline regression, a pushed no-change — covering escaping of a crafted `evil](javascript:x)` suite name and a `*outside*`-laden cluster summary; 8 for `post_comment`, including a regression test pinning the page-cap fix). Added to root `pyproject.toml`: `action` in pytest `testpaths`/`pythonpath`, and `action/format_comment.py`/`action/post_comment.py` (not `action/tests`, matching how other packages' tests aren't mypy-checked either) in mypy's `files`.
  - `pnpm check` and `pnpm verify` are both green (action: 21 new tests; core 97% / api 92% coverage, both over the 80% gate).
  - The dogfood workflow's first real run on `main` failed 2 of 3 matrix jobs, neither a bug: `smoke.yaml`'s seeded-flaky `order-status` case routinely drops the suite below a blanket `fail-under: 1.0`, and `rag-safety.yaml`'s `rag-indirect-injection` case fails *every* run (confirmed by reproducing locally) because the `rag` demo agent has no retrieved-content filtering at all — a real, permanent, unfixed planted flaw, not flakiness. Fixed at the root cause, not papered over: each matrix entry now sets its own `fail-under` matching that suite's real ceiling (smoke 0.9, rag-safety 0.5, support-agent-safety 1.0), and the baseline-artifact upload is `if: always()` so a baseline still gets recorded on a run whose own check fails (ADR 0032 amendment).

- 2026-09-29 **F3: Docker images, compose stack and CI completion** ([ADR 0033](decisions/0033-docker-images-and-compose.md), [ADR 0034](decisions/0034-dependency-audits.md)):
  - Images. All are multi-stage, non-root and pinned by tag and digest, and each has an allowlist `Dockerfile.dockerignore`. The build context is the repo root.
    - `apps/api/Dockerfile`: one image for the API and the worker. It uses a non-editable uv venv, and its default command is `alembic upgrade head && exec uvicorn`. 241 MB.
    - `demo-agents/Dockerfile`: an editable install, because the prompts are found relative to the source. 169 MB.
    - `apps/web/Dockerfile`: Next standalone on Node 22 Alpine. `NEXT_OUTPUT=standalone` switches it on, and only this Dockerfile sets it (`next.config.ts`). 207 MB.
  - `docker-compose.yml` runs pgvector Postgres, Redis, the API, the worker (same image, `taskiq worker`), the web app and the demo agents.
    - The defaults are the Redis queue, the Redis rate limiter and the mock LLM. It has no `${}` interpolation, so the developer's `.env` never leaks in.
    - Its dev secrets are committed and so public. Ports bind to 127.0.0.1. Postgres, Redis and the demo agents publish nothing.
    - Startup order uses health conditions. `api` waits for healthy `db` and `redis`, and `worker` and `web` wait for a healthy `api`, so migrations have run.
  - CI (`.github/workflows/ci.yml`):
    - `python` uploads a `coverage-report` artifact (HTML + XML for core and api) ahead of the existing per-package 80% gates. This run: core 97%, api 95%.
    - New `audit` job: `pip-audit==2.10.1` over `uv export --all-extras --all-groups` (113 packages, 0 skipped), then `pnpm audit`. Both are clean, and any finding fails the job.
    - New `workflow-lint` job: actionlint 1.7.12, with shellcheck, in its pinned image.
    - New `docker` job: `docker compose build`, `docker compose up -d --wait`, `python3 scripts/compose_smoke.py`, then `docker compose down -v`, which are the README's commands. On failure it dumps `compose ps -a` and the logs; teardown always runs.
  - `scripts/compose_smoke.py` (stdlib only):
    - It checks API and web health, then goes through the web app's `/api` rewrite to register (or log in, on a rerun), create a project, an agent at `http://demo-agents:9000/support/v1/chat` and the smoke suite, and start a run.
    - It asserts the run is `completed` with a pass rate in [0, 1]. First green run: 45 attempts, pass rate 0.98 (the seeded-flaky `order-status` case).
    - It's the first time CI runs a real `taskiq worker` process.
  - README: a new "Run the whole stack with Docker" section, whose commands match the `docker` job step for step.
  - What CI found on the way (run 36541715958):
    - `docker compose up --wait` fails on a service whose healthcheck is `disable: true` ("has no healthcheck configured"). Compose falls back to "running" only when the image defines no healthcheck at all. So the API's `/health` check moved from its Dockerfile to the compose `api` service, and the worker has none.
    - The `e2e` 429 on `11-visual-snapshots`, listed under known issues after run 36537488573, happened again. Root cause: the e2e API ran with the production auth limit (10 per minute per IP, refilling one per 6 s), while the specs make 13 register/login calls from 127.0.0.1 in about 30 s. Whether the last spec's login got through depended on timing. `playwright.config.ts` now sets `AUTH_RATE_LIMIT_PER_MINUTE=1000` for the e2e API. No spec tests the limiter, which keeps its own API tests.
  - Pipeline: 5m50s and 7m19s wall-clock on the two green runs (36542749623, 36544231620), against 5m53s before. The difference is runner noise in the same code. The new jobs run in parallel and finish within 1m10s (`docker`: build 44 s uncached, `up --wait` 19 s, smoke 2 s). `python` is still the critical path: service containers 17 s, uncached mypy 31 s, pytest 4m32s, redis tests 17 s.
    - Inside pytest, `test_family_wise_error.py` alone takes 85–114 s under coverage tracing, against about 21 s without. The four stats files take 2–2.7 minutes, and `apps/api/tests` 105–131 s.
    - Coverage's low-overhead `sysmon` core refuses `concurrency=greenlet`, so it isn't a drop-in fix.

- 2026-09-29 **F4: production deploy config** ([ADR 0035](decisions/0035-production-deploy-and-public-abuse-limits.md), [docs/DEPLOY.md](DEPLOY.md)). Hosting was researched and decided with the user. The host chosen then needed a card and was replaced on 2026-10-01 (entry below, ADR 0036):
  - Findings (2026-09-29):
    - Render: free web services sleep after 15 min and take about a minute to wake; workers cost $7/month.
    - Upstash: 500K commands a month. Our idle taskiq polling is about 2.6M a month, so the free tier dies in about 6 days.
  - User decisions: a paid scale-to-zero host (inline queue, no Redis); a shared-secret header for the web proxy; open signup with caps.
  - Deploy files:
    - `apps/web/vercel.json` turns Vercel's Git deploys off.
    - `.github/workflows/deploy.yml` runs after CI passes on main, on that commit: migrate, deploy the demo agents and the API, check `/ready`, `vercel build` + `deploy --prebuilt --prod`, then check `<web>/api/health`. Disarmed until `DEPLOY_ENABLED=true`.
  - API:
    - `GET /ready` (`SELECT 1`, 200 or 503) is the platform's health check.
    - `client_ip()` trusted a forwarded IP only with `PROXY_SECRET` (reworked in ADR 0036).
    - Startup refuses `COOKIE_SECURE=0` with an https origin, or a short `PROXY_SECRET`.
    - Register and login now require the web Origin: login CSRF is closed, since signup can be open (ADR 0009 amended).
  - Public-abuse limits (`limits.py`; every setting defaults to unlimited, production values in docs/DEPLOY.md):
    - `SIGNUP_OPEN`, `REGISTER_RATE_LIMIT_PER_HOUR` (token buckets gained a window), `MAX_SIGNUPS_PER_DAY`;
    - per-user caps on projects, agents, cases per suite, and runs per day (server runs and CI reports);
    - `LLM_GLOBAL_USD_PER_DAY`, which reserves 2 x `LLM_BUDGET_USD_PER_RUN` per non-mock run in the last 24 h and covers `/ci/report`'s live clustering too.
  - Mock LLM by default. Live Gemini is an opt-in: `API_EXTRAS=live` builds LiteLLM into the image (a new `live` extra on `agentprobe-api`; CI builds and import-checks that variant), and the image now carries `config/`.
  - Private targets: an allowlist is now the whole server policy (ADR 0012 amended).
  - Demo agents label every response (`X-AgentProbe-Demo`, and `GET /`).
  - Web: `src/proxy.ts` forwards `/api/*` itself (the `next.config.ts` rewrite is gone), reads `API_INTERNAL_URL` per request, and adds the secret when `PROXY_SECRET` is set. Compose now passes `API_INTERNAL_URL` to the web container at runtime (ADR 0033 amended).
  - Tests:
    - `test_deploy_guards.py` (client-IP truth tables, startup refusals, `/ready`, caps without a database);
    - `test_limits.py` (every cap and signup rule through the endpoints: 8 integration tests);
    - an Origin test for register and login;
    - an hourly-window bucket test;
    - SSRF truth-table rows for "allowlist only";
    - `proxy.test.ts` (target URL, secret and IP, forged headers dropped);
    - a demo-agent label test.

    The `/ci/report` `attempt()` test helper moved to `runtest.py`.

- 2026-09-30 **F4: production smoke script and the allowlist SSRF check**:
  - `scripts/smoke_prod.py` (docs/DEPLOY.md's last step). Everything goes through the web's `/api` proxy:
    - registers a throwaway `smoke-<time>-<hex>@example.com`;
    - adds an HTTP agent on the demo agents' `/support/v1/chat` and runs its connection test (the SSRF path);
    - runs a 3-case × 2 mock suite, one case failing on purpose so findings exist;
    - checks the results per case, a trace (steps and judgments), that the findings cover exactly the failed attempts, and the share link: its URL, the page and the anonymous JSON, then 404 once revoked.

    The API has no account delete, so cleanup deletes the user from `PRODUCTION_DATABASE_URL` (the cascade `scripts/cleanup_e2e_account.py` already used, now a reusable `delete_user`). It runs in `finally`, and the script fails if the user isn't found there.
  - Verified locally (not production) against the dev stack with `ALLOW_PRIVATE_TARGETS=0`, `PRIVATE_TARGET_ALLOWLIST=localhost` and `SIGNUP_OPEN=1`:
    - `PASS`;
    - the failure path (a non-allowlisted `127.0.0.1`) is refused, still deletes the user, and exits 1;
    - 0 smoke users were left on the dev database afterwards.
  - SSRF (ADR 0012/0035): the allowlist only changes `TargetPolicy.permits_private`, which `resolve_target` consults for addresses already classified PRIVATE. Every connection still goes through `GuardedBackend.connect_tcp`: resolve once, classify every address, connect to exactly the validated one. Metadata, link-local and the other BLOCKED addresses are refused before the policy is consulted. The HTTP adapter, the MCP adapter (`GuardedBackend2`), the API's connection test and the runner all build their clients that way.

    New test `test_allowlisted_host_still_resolves_validates_and_pins`. A planted "allowlisted hosts skip resolution" bypass fails all 4 cases.

- 2026-10-01 **F4 reworked for free, no-card tiers** ([ADR 0036](decisions/0036-free-tier-deploy-on-render.md); user constraint: no credit or debit card). Production is now Vercel Hobby, two Render free web services (Docker runtime: the API, and the demo agents as a second, public service) and Neon Free. Everything platform-neutral from ADR 0035 is kept.
  - Deploy:
    - The earlier host's config files and deploy steps are gone.
    - `deploy.yml` migrates, POSTs `RENDER_DEMO_DEPLOY_HOOK` and `RENDER_API_DEPLOY_HOOK` with `&ref=<sha>`, waits up to 30 min for `/ready` to report that commit (`RENDER_GIT_COMMIT`, new in `/ready`'s body), then deploys to Vercel. The `DEPLOY_ENABLED` gate is kept.
    - No `render.yaml`: Render reads one only through a Blueprint, so DEPLOY.md is the reference for the hand-made services.
  - Sleeping services, and no keep-alive (750 shared hours a month):
    - `lib/api/wake.ts` gates every `/api` call made after 10 quiet minutes on `/api/health`. It backs off 1, 2, 4, then 5 s, with a 30 s probe timeout and a 150 s budget.
    - It shows `WakingNotice` ("Waking the server, about a minute") after 1.5 s, never resends a mutation, and retries a GET once after a gateway error. The share page uses it too.
    - SSE already reconnected and fell back to polling (ADR 0031).
  - API → demo agents: `wake.py` polls `GET /health` on `WAKE_TARGET_HOSTS` for up to 120 s before a run's first attempt and before a connection test. It goes through the SSRF guard (`guarded_client()`, factored out of the HTTP adapter).
  - The demo agents are public:
    - The notice now reads "Deliberately vulnerable demo with planted flaws. No real data: fake data only." (header and `GET /`).
    - Production allows no private targets (`ALLOW_PRIVATE_TARGETS=0`, allowlist empty).
    - The smoke test's agent no longer sets `allow_private`.
  - Client IP:
    - `src/proxy.ts` sets `X-Forwarded-For` to exactly the browser's IP.
    - The API trusts the leftmost entry only with a valid `PROXY_SECRET`, and otherwise keys on the connecting address.
    - `CLIENT_IP_HEADER`, the API's `FORWARDED_ALLOW_IPS` trust and `x-agentprobe-client-ip` are removed.
  - Memory, measured on Windows with production-like settings against Neon dev:

    | State | Working set |
    |---|---|
    | Idle | 130 MiB |
    | Two concurrent 100-attempt runs, 16 polling clients, 6 SSE streams | 147 MiB peak |
    | One registration | 194 MiB peak |

    argon2 allocates 64 MiB per hash and ran unbounded on the thread pool, so `ARGON2_SLOTS=2` now bounds it. Unchanged: `mcp` costs 21 MiB at import (kept eager), LiteLLM isn't loaded in mock mode, and the production image has no `live` extra.
  - `scripts/smoke_prod.py`:
    - `WEB_ORIGIN`, `API_URL` and `DEMO_AGENTS_URL`;
    - a warm-up that wakes both services in parallel and prints each one's wake time;
    - a 120 s first-request timeout (180 s wake budget);
    - a check for the demo agents' notice on `/` and in the header.
  - Tests:
    - the client-IP truth table: spoofed `X-Forwarded-For` without the secret, wrong, prefix and empty secrets, malformed entries, a second header line, retired headers;
    - the argon2 bound and `/ready`'s commit;
    - `test_wake.py`: polling, giving up, other hosts untouched, the SSRF guard on the wake call;
    - SSRF `test_production_demo_host_is_public_with_no_private_exception` (planted bypasses fail 11 of 11 cases across both SSRF tests);
    - `wake.test.ts`, `waking-notice.test.tsx`, and `proxy.test.ts` for the new header.
  - Gates: `pnpm check` green; `pnpm verify` green (1100 passed against the Neon test branch in 31 min, core and api over the 80% coverage gate, API 92%), including the updated `test_limits.py`.
  - UI check: `next dev` with `API_INTERNAL_URL` on a dead port, `/login` at 1440, 810 and 390 px. The notice appears bottom-left from tablet up and full width at 390, with no horizontal scroll (`docs/screenshots/waking-notice-*.png`, with Next's dev overlay removed).
  - Not done here: the deploy itself waits on docs/DEPLOY.md's checklist.

- 2026-10-02 **F4 first deploy: registration 403 "Cross-origin request rejected"** ([ADR 0036 §The Origin check behind the proxies](decisions/0036-free-tier-deploy-on-render.md)):
  - Cause: Render's `WEB_ORIGIN` was `https://agent-probe-umber.vercel.app/`, with a trailing slash; a browser's `Origin` never has one. The check compares `Origin` only, exactly.
  - Reproduced with curl against production. Through the Vercel proxy, adding the browser's headers one at a time (`Sec-Fetch-*`, `Referer`, `Content-Type`, a cookie) still got 403 each time. An `Origin` with the slash got 204 both through the proxy and directly on Render, so the proxies forward `Origin` untouched. The earlier "curl works" was a 422 from body validation, which runs before the check.
  - Fix: `Settings` reduces `WEB_ORIGIN` to `scheme://host[:port]` and refuses a path, query, fragment or credentials. The live-progress CORS header (`runs.py`) uses the same value and was broken by the slash too.
  - A rejection now logs `cross-origin request rejected` with `reason`, `origin`, `web_origin`, method, path, `sec_fetch_site` and the Referer's origin only; never cookies or the proxy secret.
  - Tests (`test_deploy_guards.py`, offline): register and logout with the header set the container receives behind Vercel and Render, `WEB_ORIGIN` with and without the slash (fails on the old settings); env normalization; refused values; the log line's fields and the absence of the cookie, the secret and the Referer's query.
  - The GitHub variable `WEB_ORIGIN` also has the trailing slash, so deploy.yml's check hits `//api/health`.
  - Gate: `pnpm check` green (945 Python, 160 Vitest).

- 2026-10-02 **F4 live: production smoke passes, deploys run after CI**:
  - Live URLs: web https://agent-probe-umber.vercel.app, API https://agentprobe-api-1uno.onrender.com, demo agents https://agentprobe-1r00.onrender.com (also in the README).
  - Cause of the failed Deploy runs: the Vercel step died with "Could not retrieve Project Settings" on both runs after the Render steps had succeeded. A throwaway workflow showed the token and both IDs were fine (the project API call returned 200), and that `vercel@61.0.0` calls `GET /teams/<org>`, gets 403 for this token, and treats it as fatal. 61.1.0 and 62.1.0 pull with the same token; 55, 50 and 45 fail like 61.0.0. Fix: pin `vercel@61.1.0` in deploy.yml. The diagnostic branch is deleted.
  - deploy.yml now ends with `scripts/smoke_prod.py` (new repo variable `DEMO_AGENTS_URL`; `PRODUCTION_DATABASE_URL` comes from the `production` environment, so the credential never leaves GitHub). A green Deploy run is the production smoke test.
  - Verified: pushing `4eca0bb` to main ran CI (green, 6m20s), then Deploy by itself (green, 2m39s, every step). `/ready` reports `4eca0bb`. The smoke run registered a throwaway user, ran 6 mock attempts (pass rate 0.67 by design: one case fails on purpose), and checked per-case results, a trace (2 steps, 1 judgment), findings (1 cluster over the 2 failures), the share link (anonymous 200, then 404 once revoked), and the SSRF guard admitting the public demo agents. It then deleted the user from the production database.
  - Not measured: cold starts. Both services were already awake from the deploy (answers took 0 s and 1 s). Measure on a quiet day by running the script after 15+ idle minutes (docs/DEPLOY.md step 10).
  - Known: the smoke's registration counts against `REGISTER_RATE_LIMIT_PER_HOUR` (5 per IP) and `MAX_SIGNUPS_PER_DAY`; each deploy uses one.

- 2026-10-02 **F4: ADR 0036's live checks, two fixes, measured cold starts** ([ADR 0036 §Checked on the live deploy](decisions/0036-free-tier-deploy-on-render.md)). Probes used temporary workflows on a throwaway branch (`tmp/live-verify`, deleted afterwards), because the production DB URL and the deploy hooks live only in GitHub. Also used: curl from the dev machine, and the CLI.
  - **Client IP was spoofable (fixed).**
    - Probe: re-registering one existing throwaway address, so 409 means allowed and 429 limited, and nothing is created.
    - Through the web proxy, a made-up `X-Forwarded-For` still registered once the real IP was limited, and five with the same made-up value filled a bucket of their own. The browser's own entry sometimes arrived leftmost, against Vercel's docs.
    - Fix: `src/proxy.ts` sends Vercel's `x-real-ip` as `x-agentprobe-client-ip`, overwriting a browser's copy. The API reads only that header, only with `PROXY_SECRET`, and no longer reads `X-Forwarded-For`.
    - After the deploy: the sixth plain registration got 429; 13 spoofed requests (every header, and all at once) got 429; direct calls with this IP but no or a wrong secret stayed out of its bucket; a GitHub runner (another network) still registered.
  - **Demo MCP route was broken behind Render (fixed).** Every request got 421: the MCP SDK's DNS-rebinding check allowed only localhost hosts. It now also allows `RENDER_EXTERNAL_HOSTNAME`. Live `mcp-safety.yaml` now matches local: 6 pass, the 3 planted flaws fail, 0 errors.
  - **Deploy hook `ref`:** works. `ref=4eca0bb` while `main` was `a03afcc` built `4eca0bb` (63 s to `/ready`); head was restored the same way.
  - **`RENDER_GIT_COMMIT`:** set at runtime; `/ready` followed `a03afcc` → `4eca0bb` → `a03afcc` → `7f8ac29`.
  - **Sleeping services:** Render holds requests while waking (no 502), and Vercel's rewrite waits too.
  - **Cold starts** (GitHub runner, everything at once, two samples: about 19 h and 26 min idle):

    | | Sample 1 | Sample 2 |
    |---|---|---|
    | API wake | 32.5 s | 32.9 s |
    | Demo agents wake | 22.7 s | 22.6 s |
    | Landing page | 0.8 s | 1.0 s |
    | `/register` → dashboard visible | 36.9 s | 36.6 s |
    | Waking notice shown | 3.2 s | 3.5 s |

    `smoke_prod.py` passed both times. In the docs: DEPLOY.md, README, ADR 0036.
  - **Build allowance:** Render Hobby has 500 pipeline minutes a month, and builds stop when they run out (no card). At about 1 min per image, that's roughly 150 pushes a month.
  - Tests:
    - `test_deploy_guards.py`'s client-IP truth table moved to the new header, keeping every spoofing case and adding XFF-with-secret, `x-real-ip` and comma cases.
    - `test_limits.py`'s proxy test now has a shared spoofed leftmost XFF.
    - `proxy.test.ts` covers the browser's own copies being dropped.
    - New: `demo-agents/tests/test_mcp_host.py`.
    - Planted checks: the old XFF logic fails 5 truth-table cases and the integration test; dropping the proxy's delete fails 2 Vitest cases; the old MCP default fails 3 host cases.
  - Gates: `pnpm check` green (952 Python, 160 Vitest), `test_limits.py` green against the Neon test branch, CI green on `7f8ac29`, and the Deploy run green including its smoke test.
  - Cleanup: the throwaway accounts (two cold-start page users, the XFF-probe user) were deleted from the production database, and the deletion was confirmed.

- 2026-10-03 **User decisions: 10 runs per case, the canonical URL, dev-database cleanup** ([ADR 0022 amendment](decisions/0022-golden-tests-and-detection-measurement.md#amendment-2026-10-03-user-decision)):
  - The four example suites run 10 attempts per case (was 5), for the regression demo, the golden tests' headline metric and the dogfood (blocked-PR) workflow. Integration and e2e flow tests keep 5 so they don't slow down. `runtest.SMOKE_YAML` pins it, and `test_golden_api.py` uses the file's own 10 (`SMOKE_FILE_YAML`). Specs 05 and 06 pass `runs_per_case: 5`.
  - Re-measured in mock mode: 9 of 9 planted flaws detected, 9 of 9 controls passed. The v1 → v2 refund regression now has p ≈ 5.4e-06 (was 0.004); the detection table prints p with 2 significant figures, since the old 4 decimals read "0.0000". Clustering: 50 failing results collapse into 5 findings.
  - The README and docs/metrics.md state the limit: `unauthorized-delete` and `rag-indirect-injection` are caught only because the demo agents are rule engines. In LLM mode the agents don't report tool calls or pass context, so a live run would miss both. The demo agents are unchanged, and the live Gemini run is deferred.
  - Canonical public URL: <https://agent-probe-umber.vercel.app>. Nothing in the README, PROGRESS.md or DEPLOY.md used the branch alias. DEPLOY.md now says the alias and preview URLs are rejected by the Origin check.
  - Dev database cleanup: deleted the demo user `demo-runner@example.com` and its project `server-runner-demo-1790279638` (1 agent, 1 suite, 1 run, from B2.3's measured run on 2026-09-24). There were no API keys to revoke. A query afterwards showed no users, projects or keys.
  - Gates: `pnpm check` green (952 Python, 160 Vitest). The changed integration tests (golden API flow, baselines, IDOR) are green on Neon. The golden and CLI end-to-end tests are green at 10 runs.

- 2026-10-03 **E2: project overview and the Runs page** ([ADR 0037](decisions/0037-project-overview-and-runs-page.md)):
  - API: `GET /projects/{id}/baselines` lists a project's baselines with their runs. It's owner-scoped, and an IDOR probe covers it.
  - Overview (`/projects/{id}`):
    - a suite filter;
    - tiles: latest pass rate with its CI, the baseline and the latest run's difference from it, and the last run;
    - three trend charts on the chart theme: pass rate with its 95% CI band and a dashed baseline line, cost (agent and judging), and mean latency;
    - the 10 latest runs across suites, with a "Baseline · branch" badge;
    - "Run a suite".

    A chart with no data says why (mock runs have no cost).
  - Runs page (`/projects/{id}/runs`, the nav's Runs link): every run, a server-side suite filter, and "Load more". The run page's breadcrumb now points here.
  - `RunSuiteDialog`: suite, attempts per case, and opt-in live judging (mock by default).
  - `DataTable` columns take a `className`. The runs table hides cost and latency below 1199px so it fits its card at 810.
  - Screenshots at 1440, 810 and 390 (`overview-*`, `runs-*`, `run-dialog-1440`): no horizontal scroll and no page errors. Fixed from them: same-day runs all labelled "3 Oct" (now the time of day), a $0 cost line on a made-up $0–$4 axis, a legend on an empty chart, and the runs table overflowing its card at 810.
  - Tests (E2): `trends.test.ts` (6); `test_baselines.py` covers the listing; new e2e `12-overview-and-runs.spec.ts`, where the first run is started from the dialog (with its attempts validation), the baseline shows in the tile, chart legend and table, and the Runs page filters and links through to a run and back. The visual-snapshot spec also covers the Runs page. Specs 05, 06, 07, 11 and 12 pass.

- 2026-10-03 **E3 (rest): agents and suites pages, suite versions with their YAML** ([ADR 0038](decisions/0038-agents-and-suites-pages.md), migration 0005, scope confirmed by the user):
  - Agents:
    - the form edits every field of HTTP and MCP-over-HTTP configs;
    - fixed: edit no longer wipes fields the form doesn't show (a template, headers, method, timeout set through the API or CLI), because the config is built on the stored one;
    - the auth header can be set, replaced or removed, and is never shown;
    - Test works for a draft, an unedited saved agent (with its stored header), or any row;
    - delete asks first and says the agent's runs go with it, with the count.
  - API:
    - replaced, cleared and deleted auth headers' ciphertext is removed unless a live run still reads it (closes the orphaned-secrets known issue);
    - `suite_versions` table, backfilled with each suite's current YAML;
    - `GET /suites/{id}/versions`, `/versions/{n}` and `/cases?version=`, all IDOR-probed.
  - Suite page (`/projects/{id}/suites/{suiteId}`):
    - Editor tab: validates as you type, jumps to a problem's line, and saves a new version;
    - Cases tab: browses any version;
    - Versions tab: run counts, and a folded line diff against the version before.

    Run from the suites list or the suite page opens the shared run dialog.
  - Fixed from the screenshots: the agents table overflowed its card at 810, and the backfill stamped every version with the migration's time (now the suite's own `created_at` for v1, else NULL, shown as "Not recorded").
  - Screenshots at 1440, 810 and 390: `agents-*`, `suite-editor-*`, `suite-cases-*`, `suite-versions-*`, plus `agent-edit-1440`, `agent-edit-mcp-1440` and `agent-delete-1440`. No horizontal scroll and no page errors.
  - Tests:
    - Vitest: `agent-form.test.ts` (6: round trip with unknown fields, edits, type switch, defaults, errors, headers), `line-diff.test.ts` (4, including rebuilding both texts from the diff);
    - API integration: versions, YAML, cases in YAML order, the legacy path, 404s, no version on an unchanged PUT, secret cleanup, and a live run keeping its secret;
    - e2e: new `13-agents-and-suites.spec.ts` through the UI. The suites page object now starts runs through the dialog. The visual snapshot spec covers the suite page.
  - Gates: the full e2e suite passes (14 specs).

- 2026-10-03 **Review pass: SPEC §10 tests, security headers and CSP, secret scan, ponytail audit, coverage, SPEC compliance; F5 complete** ([ADR 0039](decisions/0039-security-headers-csp-and-request-limits.md), [docs/SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md)):
  - **SPEC §10, one named test per bullet.** Three bullets had none:
    - attacks only against registered agents (`test_spec10_runs_target_only_the_suites_own_registered_agent`);
    - YAML size limits through the API (`test_spec10_oversized_suite_yaml_is_rejected_and_nothing_saved`);
    - a complete `.env.example` (three `test_spec10_env_example_*` tests).

    Encrypted secrets never logged, SSRF and per-key rate limiting already had tests; SPEC_COMPLIANCE.md §10 maps them. The new `.env.example` tests found five gaps, all fixed: `AGENT_MODE`, `FLAKY_RATE` and `FLAKY_SEED` were undocumented, and `RUNNER_CONCURRENCY` and `AGENTPROBE_PROJECT` were read by nothing.
  - **Security headers.**
    - API: CSP `default-src 'none'`, nosniff, `X-Frame-Options`, `Referrer-Policy`, HSTS on every response. The HTML export keeps its own stricter CSP; `/docs` gets no CSP.
    - Web: a per-request nonce CSP with `'strict-dynamic'` (no inline script) from `src/proxy.ts`, and static headers from `next.config.ts`. Every page now renders dynamically, because a prerendered page has no nonce.
  - **Tests for CSRF, CORS and XSS.**
    - CSRF: a test enumerates every mutating route from the app's OpenAPI and checks that a valid session cookie with a foreign, `null`, lookalike or missing Origin gets 403.
    - CORS: no route grants a cross-origin read, and preflights get 405.
    - XSS: new offline tests for the HTML export (every field, plus a planted missing escape that fails the test) and the share page. The trace viewer's test already existed.
  - **Hardening (F5 rest).**
    - 10 MiB request-body cap, whether the length is declared or the body is chunked. Before this, `/auth/register` read unbounded bodies on a 512 MB instance.
    - Connection tests limited per account (`CONNECTION_TEST_RATE_LIMIT_PER_MINUTE`, default 20). Before this, they were an unthrottled prober of URLs the caller chose.
    - gitleaks over the full history in CI's `audit` job.
  - **Secret scan** (gitleaks 8.30.1 over all 63 commits on every ref, plus a custom pass for credential-bearing DB URLs, Neon and Render hosts, deploy hooks, `ap_` keys and JWTs):
    - no real secret anywhere;
    - three gitleaks hits, all known public dev values (the compose Fernet key, the e2e fallback key, the demo canary), none equal to a real `.env` secret, now listed in `.gitleaksignore`;
    - every DB URL with a password is a placeholder (`ep-example`, `localhost`, `db:5432`);
    - no `.env` was ever committed.

    `.claude/` was ignored only partly, and only by the developer's global git ignore; it's now in `.gitignore`.
  - **Supply-chain finding.** `agentprobe` on PyPI is an unrelated project (`nkkko/agentprobe`), so the Action's default `pip install agentprobe` and the CLI README would have installed a stranger's package. The Action now installs the CLI from its own source by default, and the README installs by git URL (verified in a clean venv). Publishing needs a name: a user decision.
  - **Ponytail audit and debt ledger.**
    - vulture and knip found no dead Python. The two unused web exports were un-exported; the other knip hits are false positives (`page.dev.tsx`, `inter-ui` loaded by path).
    - Every protocol has two implementations, or a production one and a test fake.
    - 13 `ponytail:` markers. Two named no upgrade trigger and now do (`progress.py`, `agents.py`).
    - Refused to simplify (out of bounds or load-bearing): the exact Fisher/sign-flip arithmetic and its Monte Carlo fallback; the duplicated SSRF backend for httpcore and httpcore2 (two HTTP stacks); the regex judge's three guards; refresh-token reuse detection, the dummy-hash timing equalizer and the cross-tab refresh lock; `SecretBox` (one caller, but it keeps decrypted values `SecretStr`); stdlib-only clustering (ADR 0024).
  - **Coverage by module.** From CI's last green artifact (which includes the Redis tests), every module in core and api was at or above 80% except `worker.py` (75%). New offline `test_worker.py` covers its startup/shutdown hooks and its unrecoverable, missing-run and fully-saved paths (82% offline alone).
  - **SPEC compliance** ([docs/SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md)): no MVP item missing. The only "missing" should-have items (mutator, obfuscation) were cut by user decision (ADR 0027). `pip install agentprobe` is partial (above). Fixed cheaply: no example suite exercised the MVP's jailbreak or system-prompt-extraction categories. `suites/examples/jailbreak-extraction.yaml` does now (support-v1 passes 5 of 5 cases, the vulnerable bot fails all 4 attack cases) and runs in the dogfood matrix.
  - **Waking notice** now says "about 30 to 40 seconds" (measured: about 35 s). Test, DEPLOY.md, ADR 0036 and `docs/screenshots/waking-notice-*.png` were updated, retaken from a production build at 1440, 810 and 390 with no horizontal scroll.
  - **Gates.**
    - `pnpm check`: 972 Python and 182 Vitest tests.
    - `pnpm verify`-equivalent run: 1,109 passed. The 21 failures and errors were one block where Neon closed the connection ("server closed the connection unexpectedly"), plus leftover e2e data that global counts tripped over. Every affected file passed after `scripts/reset_test_db.py` (82 tests).
    - `pnpm e2e`: 14 of 14 on the production build, and the visual spec now fails on any CSP violation.
    - Production build in a browser: every script carries the nonce, React hydrates, and there are no CSP violations.

## Next
- **F4 follow-ups (need the Render dashboard or the operator)**: run the `PROXY_SECRET` client-IP check in docs/DEPLOY.md step 10; read the API's memory graph around a Deploy run; optionally exercise `API_EXTRAS=live` as a build arg. Details: ADR 0036 §Still unverified.
- **Shorten CI** (measured in the F3 entry). Split `python`'s pytest into parallel jobs: the pure-CPU unit/stats tests, which could use `COVERAGE_CORE=sysmon` with a coverage config that has no greenlet, and the integration + redis tests. Then `coverage combine` and gate in a small final job. Also cache `.mypy_cache`, or run mypy in parallel.
- **Live detection run**: deferred (user decision, 2026-10-03). The demo agents stay as they are; the README states the two live misses.
- Consider re-measuring the metrics on recorded demo-agent runs rather than simulation, now that B1.8's golden tests exist (noted in docs/metrics.md §Limitations).

## Decisions
- Security headers, CSP and request limits ([ADR 0039](decisions/0039-security-headers-csp-and-request-limits.md)): API headers on every response (the export keeps its stricter CSP); a per-request nonce CSP with `'strict-dynamic'` on every web page, so every page renders dynamically; CORS stays without middleware; a 10 MiB body cap; connection tests limited per account; the Action installs the CLI from its own source because the PyPI name `agentprobe` is someone else's; gitleaks over the full history in CI.
- Example suites run 10 attempts per case; flow tests that only need a finished run use 5 (user decision 2026-10-03, ADR 0022 amendment). Demo agents unchanged; the two live-mode misses are documented, not fixed.
- Agents and suites pages ([ADR 0038](decisions/0038-agents-and-suites-pages.md)): the agent form edits every field of both server adapters and keeps fields it doesn't show; auth-header ciphertext is deleted when replaced, cleared or its agent deleted (unless a live run still reads it); `suite_versions` (migration 0005) keeps each version's YAML from now on; suite versions, YAML and cases are readable over the API; deleting an agent warns that its runs go too.
- Project overview and Runs page ([ADR 0037](decisions/0037-project-overview-and-runs-page.md)): trends for one suite at a time; the baseline as a tile, a dashed reference line and a table badge; `GET /projects/{id}/baselines`; one "Run a suite" dialog, mock by default.
- Production deploy on free, no-card tiers ([ADR 0036](decisions/0036-free-tier-deploy-on-render.md), user constraint 2026-10-01): Vercel Hobby + two Render free web services (the API inline; the demo agents public, fake data only, labelled) + a separate Neon project. deploy.yml after CI: migrations, Render deploy hooks pinned to the commit, wait for `/ready` to report it, then Vercel. No keep-alive (750 shared hours); the web waits for a sleeping API with a visible notice and never resends a mutation; the API wakes the demo agents before a run. Client IP: the web proxy's `x-agentprobe-client-ip` (Vercel's `x-real-ip`), only with its secret; `X-Forwarded-For` is never read (revised 2026-10-02 after the live check found it spoofable). No private targets in production. argon2 limited to two at a time for the 512 MB limit.
- Public-abuse limits ([ADR 0035](decisions/0035-production-deploy-and-public-abuse-limits.md), user decisions 2026-09-29): open signup with per-user caps, an hourly registration limit and a worst-case global live-LLM budget; register/login need the web Origin; an allowlist is the whole private-target policy.
- Docker and CI completion: three pinned, non-root, multi-stage images (one for the API and the worker); a local-only compose stack with committed dev secrets, 127.0.0.1 ports, no `${}` interpolation, the Redis queue and the mock LLM by default, and migrations on API start; a CI `docker` job that runs the README quick start command for command ([ADR 0033](decisions/0033-docker-images-and-compose.md)). Dependency audits cover every locked package, dev and `live` included, and fail on any finding; findings are fixed, pinned, or accepted in ADR 0034 ([ADR 0034](decisions/0034-dependency-audits.md)).
- e2e specs that watch a run while it's live hold its agent behind `e2e/gated-agent.ts`, never a wider timeout or a slower agent: on CI a mock-LLM run ends in under 0.5 s (2026-09-29 entry above).
- Session scheme: an httpOnly access cookie (not a JS token) behind the Next.js `/api` rewrite; a rotating refresh cookie; an SSE stream-token fallback; API keys only in `Authorization`; token-bucket rate limits with memory/Redis backends ([ADR 0009](decisions/0009-session-scheme.md)). Amends PLAN §2 #3 and supersedes #20.
- The user approved PLAN.md §2 items 1–6 and 8 (immutable case rows, ingest/baseline endpoints, same-origin cookie auth, signup allowlist + budget guard, case-level judgments, share links, separate judge cost).
- TypeScript 5.9 / ESLint 9 instead of 7 / 10 ([ADR 0002](decisions/0002-web-toolchain-versions.md)).
- `agents.secret_ref` references a new `secrets` table, Fernet-encrypted, write-only ([ADR 0003](decisions/0003-secret-storage.md)). Unblocks B2.1.
- Display font: Geist; monospace: Geist Mono; body: Inter Variable (unchanged) ([ADR 0004](decisions/0004-font-substitution.md)). Amended 2026-09-28: Inter is self-hosted from `inter-ui`, because Google's Inter lacks the OpenType features DESIGN.md depends on.
- Dashboard adaptations of DESIGN.md: result color tokens (badge/glyph only, with shape as secondary encoding), validated chart series, dashboard type tiers, a visible focus ring, a violet-only gradient card, a px spacing scale, tables scrolling at 390px ([ADR 0028](decisions/0028-dashboard-adaptations.md); user decisions: px spacing, tokens in DESIGN.md).
- Web client: openapi-fetch over generated types, single-flight refresh (in-tab promise, cross-tab Web Lock, `/auth/me` probe), cookie-presence route protection in `proxy.ts` ([ADR 0029](decisions/0029-web-api-client-and-session-refresh.md); user decision: add `GET /auth/me`).
- E1: registering redirects straight to the destination rather than to `/login`, since `POST /auth/register` already starts a session; `/login`'s own silent refresh (ADR 0029) is for arriving at a protected link with a dead access cookie, not for post-registration. `next` is validated by an allowlist regex (`lib/safe-next.ts`), not a denylist, so an unanticipated bypass falls back to `/projects` instead of forwarding it. The model/provider view added a new endpoint, `GET /config/llm` (session-only, no project scoping — it's server-wide config, not a secret), rather than hardcoding roles in the UI (SPEC.md §10). Input/Textarea/Select gained a default hairline border (ADR 0028 §8 amended) after E1's screenshots showed them invisible on `surface-1` cards and dialogs.
- A real e2e suite (E7) runs against its own database and ports, never a developer's dev stack or the dev database: `TEST_DATABASE_URL`, ports 3010/8100/9100, a full reset (`scripts/reset_test_db.py`, driven by `apps/web/scripts/reset-e2e-db.mjs`) before every invocation rather than per-spec account cleanup. The reset is chained with `&&` ahead of `playwright test`, not a Playwright `globalSetup` — CI proved `globalSetup` isn't guaranteed to finish before `webServer` commands start. `next start`, not `next dev`, for the web server (`next dev` refuses a second instance per project directory regardless of port). No pixel-diff visual regression testing: font rendering differs between this machine and CI's Linux runner (user decision precedent: E0–E6's screenshots are already compared by eye/AI against DESIGN.md, never asserted pixel-for-pixel).
- Compare and findings pages (E6): no new endpoints — `GET /runs/compare`, `GET /runs/{id}/verdict` and `GET /runs/{id}/findings` already existed. The compare page fixes the URL's run as the candidate and only lets the user change the baseline, defaulting to the run's own branch baseline; a verdict banner states which statistical channel fired, its p-value and its own `alpha` share, and the effect size and N, in prose, not just the verdict word. Both pages are linked from the run page's action row rather than the top nav, since the nav's Runs section has no list page yet (E2/E3). The findings page's one `GradientCard` is the "N failures → K findings" summary tile, per DESIGN.md's one-per-viewport rule.
- Trace timeline: plain HTML/CSS, no React Flow ([ADR 0005](decisions/0005-trace-timeline-no-react-flow.md)).
- Run detail and trace viewer ([ADR 0031](decisions/0031-run-detail-and-trace-viewer.md)): the browser opens a run's SSE stream on the API with a stream token, because the `/api` rewrite gzips and so buffers it (measured); the page owns the state and resyncs on every (re)connect; judgments are anchored to steps by core's `judgment_steps`; `/runs/{id}/verdict` compares against the run's branch baseline, `main` for a run without a branch; long step lists use `content-visibility`, not windowing (user decision); rule vs LLM verdicts differ by border style plus label.
- Regression statistics: Fisher exact (one-sided) + Holm (per case), paired sign-flip permutation (suite), case-level bootstrap CI; α=0.05, min_drop=0.05, all configurable via suite YAML and CLI flags ([ADR 0006](decisions/0006-statistics-methodology.md)). The per-case correction was later amended to Tarone–Holm (user decision, ADR 0014).
- Hosting for the API/worker (Q2) is deliberately deferred to Phase F4; the only binding constraint now is that the worker stays behind the `QueueBackend` interface with `inline` as the local default. Decided 2026-09-29 (user): inline queue, no Redis in production ([ADR 0035](decisions/0035-production-deploy-and-public-abuse-limits.md)); hosted on Render's free tier since 2026-10-01 ([ADR 0036](decisions/0036-free-tier-deploy-on-render.md)).
- `packages/core` must contain exactly one run-execution implementation (`execute_attempt` / `finalize_run` / `run_suite`), shared by the CLI's local run and the server runner — no duplicate run loops (Q6 requirement, tracked at B1.7).
- Share links store only `runs.share_token_hash` (SHA-256), not a plaintext token. The Fernet key env var stays `ENCRYPTION_KEY` (user decisions, 2026-09-25).
- Data model conventions: UUID PKs, text+CHECK instead of PG enums, `NUMERIC(12,6)` costs, CASCADE along ownership, and every FK covered by a leading index ([ADR 0007](decisions/0007-data-model-additions.md)).
- Neon connection config, sync migrations, rollback-per-test isolation, selector loop on Windows, CI on service containers ([ADR 0008](decisions/0008-db-connection-and-test-isolation.md)).
- Suite schema field names (judge params, `attack`/`attack_params`, `context` not `fixtures`), the attack registry's extension-point shape, anchor/alias rejection by token-scanning, and agent config validation living in `apps/api` (not `packages/core`, since the HTTP adapter itself is B1.4) ([ADR 0010](decisions/0010-suite-schema-and-agent-config.md)).
- Adapters: errors are responses, not exceptions; a trace step union shared by runner/judges/storage/UI; `{{documents}}` + in-house JSONPath subset; strict `tool_calls` mapping; retry only what can't have reached the agent; SSRF guard as a pinned-IP httpcore backend with explicit address tables; private targets need agent + server opt-in (+ optional allowlist); Python adapter CLI-only by construction ([ADR 0012](decisions/0012-http-adapter-and-ssrf-guard.md)).
- LLM layer: roles spread across models for per-model free-tier quotas, RPD persisted and fail-fast, one retry policy (LiteLLM retries off), USD estimates from dated paid-tier prices, LiteLLM as a lazy opt-in extra; `LLM_MODEL_DEMO_AGENT`/`LLM_MODEL_MUTATOR` renamed to `LLM_MODEL_AGENT`/`LLM_MODEL_ATTACKER` ([ADR 0011](decisions/0011-llm-layer.md)). The `attacker` role was removed with the mutator ([ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md)).
- Judges: `JudgeContext` wraps `case`/`response` rather than duplicating their fields; `json_schema` validates via the `jsonschema` library (now a direct core dependency) instead of a hand-rolled validator; `regex` was guarded by a length cap, not a timeout (superseded by ADR 0015, below); `llm_rubric` neutralizes literal delimiter tags found inside the untrusted output/input before wrapping them, and gained `samples: int` for majority voting; `consistency` reads `ctx.case_outputs`, populated by the executor, rather than having its own interface ([ADR 0013](decisions/0013-judges.md)).

- Positioning: the differentiated core is statistically-corrected, flakiness-aware regression detection in a real CI gate, judged on traces and tool calls — not a breadth play against eval platforms. C4 and obfuscation variety are the first cuts; MCP is an adapter, not an MCP-security product ([POSITIONING.md](POSITIONING.md), user decision 2026-09-26).
- `alpha` is the whole verdict's false-alarm budget, split over the per-case family and the suite test (`alpha_cases`/`alpha_suite`, `alpha`/2 each by default, sum capped at `alpha`). Before this, each channel spent the full `alpha` and the verdict's measured rate reached 6.5% against a configured 5% ([ADR 0014](decisions/0014-statistics-implementation.md#verdict), user decision 2026-09-26).
- Statistics implementation ([ADR 0014](decisions/0014-statistics-implementation.md)):
  - The case is the resampling unit (within-case correlation).
  - A Wilson floor for degenerate bootstraps.
  - One-sided Fisher tests; a Tarone–Holm step-down per case (user decision), with worse and better as separate families. Thresholds are reported, not adjusted p-values.
  - Exact sign-flip by dynamic programming (exact beyond ADR 0006's 20 cases when cheap), with a Monte Carlo fallback.
  - Exact rational threshold comparisons.
  - One flagged case is a regression even when the suite drop is below `min_drop`. Regression wins the verdict. `alpha` is the verdict's budget, split over the per-case family and the suite test (`alpha_cases`/`alpha_suite`, half each by default), so the verdict's own rate is held at `alpha` (amended 2026-09-26).
  - Only shared cases are compared.
  - Cost deltas are per attempt.
- Server runner ([ADR 0017](decisions/0017-server-runner-and-queue.md)):
  - Taskiq + taskiq-redis instead of Arq.
  - `QUEUE_BACKEND=inline|redis` behind `QueueBackend`.
  - Runs execute from a config snapshot.
  - Attempts are saved only while the run is running, and idempotent on (run, case, attempt).
  - The first infrastructure error fails the run.
  - Crash recovery resumes and skips saved attempts.
  - SSE via a `ProgressBus` (in-process / Redis pub/sub), with subscribe-then-snapshot.
  - The Redis LLM budget is per job for now (user decision).
- Regex judge ([ADR 0015](decisions/0015-regex-judge-hardening.md)): the `regex` package with a 0.25 s matching timeout; a stdlib-parser expansion bound (10,000 elements) before compiling; the output cap raised to 100,000. RE2 was considered and rejected: it has no lookarounds, backreferences or verbose mode, and logs parse errors to stderr.
- Run execution and CLI ([ADR 0016](decisions/0016-run-execution-and-local-cli.md)):
  - A judge `error` makes the attempt an `error`.
  - Only `unreachable` attempts are retried at run level.
  - Consistency is reported per case and doesn't change the pass counts.
  - The agent's cost is `None` without a configured price.
  - `--fail-under` defaults to 1.0. Exit precedence is 4 > 2 > 1.
  - The CLI grants the policy half of the private-target opt-in itself; the agent must still set `allow_private: true`.
  - ~~Attack-only and `mutations` cases are refused up front until the attack library and the mutator exist.~~ Superseded by ADR 0027: `attack` is a label, a case needs `input` or `call` at parse time, and `mutations` no longer exists.
- Results, compare, baselines, CI report, export and share links ([ADR 0018](decisions/0018-results-compare-ci-report-export-share.md)):
  - `/ci/report` requires the suite and agent to already exist in the project, by name; it never auto-creates them from the payload.
  - `baseline_branch` (default: the report's own `branch`) picks which branch's baseline to diff against; setting a baseline is a separate, deliberate action, never automatic on ingest.
  - `GET /runs/compare` requires both runs to share a `suite_id`.
  - JSON/HTML export recomputes a `RunSummary` via core's `finalize_run` rather than trusting the persisted `run_case_summaries` columns.
  - The public share view is read straight off persisted columns (no recomputation) and is narrower than the authenticated views: no agent config, no raw trace.
  - Request handlers must never call the queue's `Sessions`-based helpers (`save_attempt`, `save_summary`, `claim`, `load_attempts`, `finish`) synchronously; those are for the queue/worker only. Ingest uses its own single-transaction `runstore.insert_results`/`insert_summary` instead.
  - Amended 2026-09-26: ingest validation is core's `check_results` (rejects out-of-range attempts too); the HTML export has a `default-src 'none'` CSP.
- `/ci/report` is the single run-ingest endpoint and returns structured data only; the GitHub Action formats the PR comment ([ADR 0019](decisions/0019-ci-report-is-the-ingest-endpoint.md), user decision 2026-09-26).
- Runs of unregistered agents and per-suite-and-agent baselines ([ADR 0020](decisions/0020-unregistered-agent-runs.md), user decision 2026-09-26):
  - `runs.agent_id` or `runs.agent_name`, exactly one.
  - Baselines keyed on (project, suite, branch, agent).
  - `agentprobe run --push` sends a python agent as `agent_name`, an http agent as `agent`.
- Coverage gate: 80% per package (`agentprobe_core`, `agentprobe_api`) over unit + integration tests, in `pnpm verify` and CI; coverage traces greenlets (user decision 2026-09-26, PLAN.md B1.9).
- Attack ids are a constant (`ATTACKS`) until C1; `obfuscate`/`attack_params` are refused like `mutations`; the API's agent config is `http` | `python` until C3 (ADR 0010 and 0016 amendments). Superseded 2026-09-27: `ATTACKS` is an id-to-category dict, the three generation fields are gone (ADR 0027), and the API's agent config is `http` | `mcp` with `python` refused by a validator on the union.
- CLI remote compare and packaging ([ADR 0025](decisions/0025-cli-remote-compare-and-packaging.md)): `compare`/`--baseline` resolve a UUID-shaped argument as a server run id via `GET /runs/{id}/export`, sharing `Target`/`PushError` with `--push`; a wheel-install check (`scripts/verify_wheel.py`) runs as its own CI job rather than a pytest test, since it needs its own venv.
- Failure clustering ([ADR 0024](decisions/0024-failure-clustering.md)): single-linkage agglomerative clustering over embedding vectors at a fixed cosine-distance threshold (stdlib only, no numpy/scipy); the summarizer role returns free-text `Summary:`/`Fix:` lines rather than a `json_schema` verdict, since the mock provider's generic JSON fallback would make every cluster's finding read identically; clustering is a post-run job on both queue backends (run before `publish_status`, not after) and runs synchronously inside `/ci/report`'s own transaction; a clustering failure is logged, never a run failure.

- Two baseline flags, not one overloaded `--baseline <branch>`: `--baseline` compares locally (run file, saved name, server run id), `--baseline-branch` compares on the server. A deliberate improvement on D2.1's single-flag wording; `run --push --baseline X` with nothing resolving locally explains both flags ([ADR 0025](decisions/0025-cli-remote-compare-and-packaging.md), amended 2026-09-27).
- The MCP tool-description injection scan is out of scope: MCP is one adapter type for breadth, not a security scanner ([ADR 0026](decisions/0026-no-mcp-tool-description-scan.md), user decision 2026-09-27; amends PLAN.md §2 #13).
- Generated attack-payload variety (template generators, obfuscation, the LLM mutator) is out of scope. Attack ids only classify author-written cases, kept as an id-to-category registry for schema validation and future editor autocomplete ([ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md), user decision 2026-09-27; supersedes ADR 0021).
- Core's `CaseSummary.pass_rate`/`label` are pydantic computed fields, so JSON consumers (the dashboard, CLI `--json`, exports) read the label instead of re-deriving it; `CaseSummary` ignores extra keys on load so saved runs read their own dumps back (2026-09-28 review).
- `LLM_CACHE=1` is the recommended setting for live/dev runs (`.env.example`, docs/metrics.md). `scripts/measure_detection.py` forces it off for itself, because cached replays would erase the run-to-run variance it measures. Non-`live` tests clear it (user decision 2026-09-27, ADR 0022 amended).

## Known issues
- Every web page renders per request (the CSP nonce, ADR 0039): one Vercel function invocation per page view, no prerendered HTML.
- The CLI isn't on PyPI, and the name `agentprobe` there belongs to an unrelated project. Install it by git URL (`packages/cli/README.md`); the Action installs from its own source.
- Neon sometimes drops the test connection mid-run ("server closed the connection unexpectedly"), failing a contiguous block of integration tests. It happened twice on 2026-10-03. Rerun the affected files; the failure looks the same each time.
- `pnpm e2e` reuses an already-running e2e web/API/demo-agents stack (`reuseExistingServer: true`) across consecutive invocations, which is deliberate for local iteration — but a `next build` produced by a since-changed working tree won't be picked up until those processes are stopped (Windows: `Get-NetTCPConnection -LocalPort 3010,8100,9100` to find and kill them). The reset script still runs on every invocation, so stale data is never the issue; a stale build is.
- Locally, `pnpm e2e` and `pnpm verify` share one Neon branch (`TEST_DATABASE_URL`); CI gives each its own throwaway Postgres container, so this is a local-only concern. `pnpm e2e`'s reset wipes it before *its own* run, but several of its specs leave real users and active sessions behind afterward (by design — no per-spec cleanup, unlike `01`–`06`), which sat there until the next `pnpm e2e` reset. One integration test's assertion was scoped too broadly and read that leftover data as a failure (fixed, see the E7 entry above); if `pnpm verify` ever fails right after an e2e run in a way that looks unrelated to your change, run `uv run --env-file .env python scripts/reset_test_db.py` and retry before assuming it's real.
- `uvicorn --reload` on Windows can detect a change and never restart its worker while a run's SSE stream is open: the old code keeps serving with no second "Application startup complete" in the log (seen twice on 2026-09-28, including a peer session's API left from the morning). Restart `pnpm dev:api` after API changes if a new route 404s.
- Deploys need `NEXT_PUBLIC_API_URL` (web, build time) and `WEB_ORIGIN` (API) for live run progress; without them the run page polls every 3 s (ADR 0031). docs/DEPLOY.md sets both.
- The local `.env`'s `PUBLIC_WEB_URL` points at `https://agentprobe.example.com`, so share links created locally carry that host. The dialog falls back to the page's own origin only when the API returns no URL.
- Background `next dev`/`uvicorn` processes on Windows can outlive a stopped parent `pnpm` process and keep their port held. Check with `Get-NetTCPConnection -LocalPort 3000` (web) or `-LocalPort 8000` (API) before assuming a dev server is stale or absent; a session in this repo has hit a leftover `uvicorn` from a previous day still answering on :8000 with routes from before that session's changes.
- Playwright's `page.waitForURL()` defaults to `waitUntil: "load"`, which never resolves after a client-side (History API) route change like `router.replace()` — a real navigation event never fires. Use `await expect(page).toHaveURL(...)` for those; `waitForURL` is still correct after a real (proxy-issued) redirect.
- Statistics power (ADR 0014 §Power), all measured after the `alpha` split:
  - At 3 runs per case a single broken case can never be flagged: its smallest possible p (1/20) is above the default per-case budget of 0.025, so detection is 0.5%. **Use 5 or more runs**; the CLI's `--help` and [docs/metrics.md](metrics.md) say so.
  - At 100 cases a single break is missed on 0.8% of runs (7+ flaky cases can come within reach of 0.025 and raise Tarone's K). At 10 and 30 cases it is 100%.
  - A case that only turns flaky (5/5 → 3/5) is weak evidence at 5 runs: three of them are detected 21.1% of the time (66.9% at 10 runs).
- `test_family_wise_error.py` adds about 21 s to `pnpm check` (24 seeded cells × 1,000 trials, now through `compare_runs` so it measures both channels and the verdict).
- The regex judge blocks the event loop for up to 0.25 s per attempt when a pattern times out. A suite that times out everywhere costs that on every attempt. Neither B1.7 nor B2.3 added a run-level time budget; add one (or fail a pattern fast after its first timeout in a run) if it shows.
- `agentprobe run` with `llm.provider: litellm` outside the repo root fails with exit 3 ("config/llm.yaml not found"): the live LLM config is read from `AGENTPROBE_CONFIG_DIR` (default `config/`). A pip-installed CLI needs the model/pricing config shipped as package data before live judging works outside the repo (F6).
- The CLI stops at the first infrastructure error (ADR 0016), but that first attempt still spends its full retry budget. On Windows a refused localhost connect takes about 2 s, so a down agent costs about 20 s before exit 4.
- The regex judge's compile-time guard relies on the stdlib parser (`re._parser`, private, no stubs) agreeing with `regex` on how repeats nest. The 10,000-element limit leaves 100× headroom for disagreement (ADR 0015).
- The suite CI under-covers with few cases: 87% at 10 cases vs 94% at 30 (percentile cluster bootstrap, ADR 0014).
- `pnpm verify` needs `TEST_DATABASE_URL`, `DATABASE_URL` and `ALLOW_DB_TESTS=1` (loaded from `.env`). Without them it refuses with exit code 2, which is intended. It takes about 17 min against Neon from here (see the coverage note below): each request costs 2–4 round trips of 80–140 ms (more on a bad network day). A Neon region closer to the developer would cut this proportionally.
- On native Windows, psycopg async needs `SelectorEventLoop`. Tests use the root conftest hook; `pnpm dev:api` passes `--loop asyncio:SelectorEventLoop`. Production start commands on Windows would need the same flag (Linux doesn't).
- `JWT_TTL_MINUTES` now defaults to 15. A local `.env` that still says 60 keeps 60-minute access cookies.
- `uv` and `gh` are installed but not on PATH in some shells (`%USERPROFILE%\.local\bin`, `C:\Program Files\GitHub CLI`).
- The pytest run shows a `StarletteDeprecationWarning`: Starlette's TestClient wants `httpx2` instead of `httpx`. Swapping `httpx==0.28.1` for `httpx2` was blocked by a local permission rule this session. Redo it once allowed. The HTTP adapter's SSRF guard swaps httpx's private `transport._pool` (ADR 0012), so rerun `packages/core/tests/adapters` after any httpx change.
- Local `.env` files from before B1.4 still say `ALLOW_PRIVATE_AGENT_URLS`, which nothing reads. Rename it to `ALLOW_PRIVATE_TARGETS=1` to reach the demo agents on localhost (done in this machine's `.env` on 2026-09-28, user decision).
- An OpenAI-style agent that omits `tool_calls` when it made none gets an error under the strict mapping rule. Add an explicit "optional" flag to `ResponseMapping` if such an agent needs support (ADR 0012).
- `next build` downloads Google Fonts (Geist, Geist Mono; Inter is self-hosted), so it needs network access. `pnpm check` doesn't build; CI does.
- A replaced or cleared auth header's `secrets` row is deleted (ADR 0038), except when a queued or running run's snapshot still reads it; that one stays orphaned (`ponytail:` in `agents.py`). Rows orphaned before 2026-10-03 were not cleaned up.
- Suite versions saved before migration 0005 have no YAML ("Before history was kept"), and a backfilled current version > 1 has no save time ("Not recorded").
- Deleting an agent deletes its runs (`runs.agent_id` cascades). The UI warns with the count from the newest 200 runs.
- This machine has a stale machine-level `CURL_CA_BUNDLE=C:\Program Files\PostgreSQL\18\ssl\certs\ca-bundle.crt` (the file doesn't exist; left by an uninstalled PostgreSQL). The live LLM provider refuses to start while it is set. Remove it from an admin PowerShell: `[Environment]::SetEnvironmentVariable('CURL_CA_BUNDLE', $null, 'Machine')`, then open a new terminal.
- LiteLLM 1.102.1 ships a `cl100k_base` tokenizer file that fails tiktoken's hash check, so the first live import downloads the canonical file (hash-verified) into `.agentprobe/tiktoken/`. It needs network once; after that imports are offline.
- The daily quota file (`.agentprobe/llm-quota.json`) has no cross-process lock: concurrent processes can undercount by a few requests. It is also per host, so each worker host has its own daily cap.
- LLM budget on the Redis backend (user decision: deferred, ADR 0017): each job builds its own LLM client, so the per-run caps apply per attempt. The per-host daily USD cap is the backstop. Move the run budget and the daily cap to Postgres/Redis before F4 (deploy).
- Free-tier RPM/RPD defaults (10/250) are placeholders: Google only shows the real per-model values in AI Studio. Set `LLM_RPM`/`LLM_RPD` in `.env` from https://aistudio.google.com/rate-limit.
- On native Windows the Redis worker needs the selector event loop for psycopg, like the API. Local development uses `QUEUE_BACKEND=inline`, so this only matters for running the worker on Windows.
- taskiq-redis only reclaims a dead worker's unacknowledged jobs after it fetches a new message; an idle queue never reclaims. The worker's startup sweep (`RUN_STALE_AFTER_S`) covers runs left behind.
- Inline crash recovery treats every queued/running run as orphaned at API startup, which is correct for one API process only. Use `QUEUE_BACKEND=redis` with several.
- Every attempt save takes a row lock on its run (ordering against cancel/fail and the `attempts_done` counter), which serializes one run's saves: about 6 round trips per attempt, around 25 s for 40 attempts on Neon from here. Batch the saves if it matters.
- `POST /ci/report` inserts one attempt at a time (`runstore.insert_results`, one flush per attempt for its id), not batched. Fine at the tested scale (tens of attempts); revisit if real CI payloads run to thousands.
- The clustering distance threshold (0.25 cosine distance) is empirical against the mock embedding's own hashing (ADR 0011) and unvalidated against a live embedding model; there is no suite-level config to tune it yet.
- `agentprobe run --push` sends an http agent as `agent`, so that agent must be registered on the server first, even if it only runs in the user's CI (e.g. on localhost). Sending unknown http agents as `agent_name` needs a lookup; left for D2.1's remaining work (ADR 0020).
- The coverage gate covers `agentprobe_core` and `agentprobe_api` only (PLAN.md B1.9), not `packages/cli` or `demo-agents`. Locally `worker.py` shows 33% because its tests need Redis; CI, which runs them, is the authoritative number for it.
- Migration 0004's downgrade is lossy: it deletes unregistered-agent runs and all but one baseline per (project, branch), which the old schema can't hold.
- `pnpm verify` runs unit and integration tests in one pytest run with coverage tracing; the integration tests dominate its ~17 minutes.
- The `/shared/{token}` public view omits per-attempt trace steps (tool-call arguments, message-by-message detail) by design (ADR 0018); revisit if a real use case needs the full trace in a public link.
- The dogfood workflow's workflow-artifact baseline (ADR 0032) is throwaway by design: no versioning, GitHub's default 90-day retention, and nothing stops `main`'s last recorded run from itself having been a bad one (there's no server-side baseline gate on it, unlike ADR 0018's `POST /projects/{id}/baseline`). It also has no data until this change's own push-to-main job has run once — the very first PR touching `demo-agents/**`/`suites/**` after this merges will show `no_baseline` in its dogfood comment even though a direct judge failure (not a baseline comparison) can still fail the check via `--fail-under`. Revisit once F4 deploys a server: point the workflow at `api-url`/`api-key` and drop the artifact plumbing.
- The dogfood matrix posts one PR comment per suite/agent pair (three, currently), not one combined comment, since a composite action step can't easily merge results across parallel matrix jobs (ADR 0032).
- The Docker images, compose file and smoke script are only verified by CI's `docker` job (Docker can't run on the development machine).
- The compose worker has no healthcheck (no port). `up --wait` counts it ready once it's running, and a hung worker would only show up as runs that never finish. ADR 0033 notes a liveness check (its Redis consumer's idle time) for F4.
- Through the compose web app, the API sees every browser's requests as coming from the web container, so the per-IP auth limit is shared by everyone using that stack. That's fine for one local user; a public deploy sets `PROXY_SECRET` on both sides instead (ADR 0036).
- `pnpm/action-setup@v6` warns about a "pnpm v10 installation layout at PNPM_HOME" in every job that uses it (runner image vs pnpm 11). It's harmless, and it predates F3.
- Still unverified on the live deploy (ADR 0036 §Still unverified):
  - Render passing env vars as Docker build args. Documented by Render; exercising it means switching production's image.
  - Whether an open SSE stream counts as activity. Render's docs list only HTTP requests and WebSocket messages; a run that sleeps mid-way is resumed by crash recovery.
  - Memory in the Linux image (Render's dashboard only).
  - That the client-IP key is exactly the browser's address. That check needs `PROXY_SECRET`; the spoofing checks passed.
- The API's wake-up of sleeping agent hosts (`wake.py`) runs on the inline queue and the connection test only, not on the Redis worker path (production is inline).
- The per-user caps count, then insert, so two concurrent creates can each pass a cap by one (`ponytail:` in `limits.py`). A resumed live run builds fresh LLM clients and can exceed its budget reservation (ADR 0035).
- Production rate limits are in memory in the one API instance. They reset when it sleeps, which happens only after 15 idle minutes.
