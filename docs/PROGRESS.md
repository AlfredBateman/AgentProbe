# Progress

## Status by phase (PLAN.md §1)
A phase is complete only when every task in it is done.

| Phase | Status |
|---|---|
| A: foundation | **Complete** (A1–A5). |
| B1: core engine | **Not complete.** B1.1–B1.7 and B1.9 (coverage gate, 2026-09-26) are done; **B1.8 (golden tests) is open.** |
| D1: CLI local run | **Complete** (D1.1). |
| B2: server runner and results API | **Complete** (B2.1–B2.6). B2.5's ingest is `POST /ci/report`, not the planned `runs:ingest` ([ADR 0019](decisions/0019-ci-report-is-the-ingest-endpoint.md)). |
| D2: CLI remote features | **In progress.** `run --push` is done ([ADR 0020](decisions/0020-unregistered-agent-runs.md)); remote `compare` and `--baseline <branch>` remain. |
| C, E, F | Not started. |

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

## Next
- Decide whether SPEC.md §1 (tagline, "pytest + Playwright + a security scanner") and §16's resume bullets should be reworded to match [POSITIONING.md](POSITIONING.md), or deliberately left as the broader scope statement.
- **B1.8: golden tests** (the last open B1 task). Fill in `demo-agents/vulnerabilities.json` `suite_case_ids` (the smoke suite covers 5 of the 7 planted flaws; instruction injection and RAG indirect injection need cases with `context`).
- D2.1 (rest): remote `compare <a> <b>` and `--baseline <branch>` against server baselines.
- Consider re-measuring the metrics on recorded demo-agent runs rather than simulation, once B1.8's golden tests exist (noted in docs/metrics.md §Limitations).
- C4: failure clustering (`GET /runs/{id}/findings`, populating `top_findings` in `/ci/report`'s response — currently always empty).

## Decisions
- Session scheme: an httpOnly access cookie (not a JS token) behind the Next.js `/api` rewrite; a rotating refresh cookie; an SSE stream-token fallback; API keys only in `Authorization`; token-bucket rate limits with memory/Redis backends ([ADR 0009](decisions/0009-session-scheme.md)). Amends PLAN §2 #3 and supersedes #20.
- The user approved PLAN.md §2 items 1–6 and 8 (immutable case rows, ingest/baseline endpoints, same-origin cookie auth, signup allowlist + budget guard, case-level judgments, share links, separate judge cost).
- TypeScript 5.9 / ESLint 9 instead of 7 / 10 ([ADR 0002](decisions/0002-web-toolchain-versions.md)).
- `agents.secret_ref` references a new `secrets` table, Fernet-encrypted, write-only ([ADR 0003](decisions/0003-secret-storage.md)). Unblocks B2.1.
- Display font: Geist; monospace: Geist Mono; body: Inter Variable (unchanged) ([ADR 0004](decisions/0004-font-substitution.md)).
- Trace timeline: plain HTML/CSS, no React Flow ([ADR 0005](decisions/0005-trace-timeline-no-react-flow.md)).
- Regression statistics: Fisher exact (one-sided) + Holm (per case), paired sign-flip permutation (suite), case-level bootstrap CI; α=0.05, min_drop=0.05, all configurable via suite YAML and CLI flags ([ADR 0006](decisions/0006-statistics-methodology.md)). The per-case correction was later amended to Tarone–Holm (user decision, ADR 0014).
- Hosting for the API/worker (Q2) is deliberately deferred to Phase F4; the only binding constraint now is that the worker stays behind the `QueueBackend` interface with `inline` as the local default.
- `packages/core` must contain exactly one run-execution implementation (`execute_attempt` / `finalize_run` / `run_suite`), shared by the CLI's local run and the server runner — no duplicate run loops (Q6 requirement, tracked at B1.7).
- Share links store only `runs.share_token_hash` (SHA-256), not a plaintext token. The Fernet key env var stays `ENCRYPTION_KEY` (user decisions, 2026-09-25).
- Data model conventions: UUID PKs, text+CHECK instead of PG enums, `NUMERIC(12,6)` costs, CASCADE along ownership, and every FK covered by a leading index ([ADR 0007](decisions/0007-data-model-additions.md)).
- Neon connection config, sync migrations, rollback-per-test isolation, selector loop on Windows, CI on service containers ([ADR 0008](decisions/0008-db-connection-and-test-isolation.md)).
- Suite schema field names (judge params, `attack`/`attack_params`, `context` not `fixtures`), the attack registry's extension-point shape, anchor/alias rejection by token-scanning, and agent config validation living in `apps/api` (not `packages/core`, since the HTTP adapter itself is B1.4) ([ADR 0010](decisions/0010-suite-schema-and-agent-config.md)).
- Adapters: errors are responses, not exceptions; a trace step union shared by runner/judges/storage/UI; `{{documents}}` + in-house JSONPath subset; strict `tool_calls` mapping; retry only what can't have reached the agent; SSRF guard as a pinned-IP httpcore backend with explicit address tables; private targets need agent + server opt-in (+ optional allowlist); Python adapter CLI-only by construction ([ADR 0012](decisions/0012-http-adapter-and-ssrf-guard.md)).
- LLM layer: roles spread across models for per-model free-tier quotas, RPD persisted and fail-fast, one retry policy (LiteLLM retries off), USD estimates from dated paid-tier prices, LiteLLM as a lazy opt-in extra; `LLM_MODEL_DEMO_AGENT`/`LLM_MODEL_MUTATOR` renamed to `LLM_MODEL_AGENT`/`LLM_MODEL_ATTACKER` ([ADR 0011](decisions/0011-llm-layer.md)).
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
  - Attack-only and `mutations` cases are refused up front until the attack library and the mutator exist.
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
- Attack ids are a constant (`ATTACKS`) until C1; `obfuscate`/`attack_params` are refused like `mutations`; the API's agent config is `http` | `python` until C3 (ADR 0010 and 0016 amendments).

## Known issues
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
- Deploy (F4) must set `FORWARDED_ALLOW_IPS` to the proxy and keep the API reachable only through it. Otherwise the per-IP auth limit is either global (every user shares the proxy's IP) or spoofable (ADR 0009 §9).
- `JWT_TTL_MINUTES` now defaults to 15. A local `.env` that still says 60 keeps 60-minute access cookies.
- `uv` and `gh` are installed but not on PATH in some shells (`%USERPROFILE%\.local\bin`, `C:\Program Files\GitHub CLI`).
- The pytest run shows a `StarletteDeprecationWarning`: Starlette's TestClient wants `httpx2` instead of `httpx`. Swapping `httpx==0.28.1` for `httpx2` was blocked by a local permission rule this session. Redo it once allowed. The HTTP adapter's SSRF guard swaps httpx's private `transport._pool` (ADR 0012), so rerun `packages/core/tests/adapters` after any httpx change.
- Local `.env` files from before B1.4 still say `ALLOW_PRIVATE_AGENT_URLS`, which nothing reads. Rename it to `ALLOW_PRIVATE_TARGETS=1` to reach the demo agents on localhost.
- An OpenAI-style agent that omits `tool_calls` when it made none gets an error under the strict mapping rule. Add an explicit "optional" flag to `ResponseMapping` if such an agent needs support (ADR 0012).
- `next build` downloads Google Fonts (Inter, Geist), so it needs network access. `pnpm check` doesn't build.
- Replacing or clearing an agent's `auth_header` orphans the old `secrets` row instead of deleting it (`ponytail:` comment in `agents.py`). Harmless (it's ciphertext, never returned) but worth a cleanup pass if the table's size ever matters.
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
- `GET /runs/{id}/findings` (SPEC.md §8) and `/ci/report`'s `top_findings` are not built yet; the latter always returns `[]` until C4 (failure clustering) exists.
- `agentprobe run --push` sends an http agent as `agent`, so that agent must be registered on the server first, even if it only runs in the user's CI (e.g. on localhost). Sending unknown http agents as `agent_name` needs a lookup; left for D2.1's remaining work (ADR 0020).
- The coverage gate covers `agentprobe_core` and `agentprobe_api` only (PLAN.md B1.9), not `packages/cli` or `demo-agents`. Locally `worker.py` shows 33% because its tests need Redis; CI, which runs them, is the authoritative number for it.
- Migration 0004's downgrade is lossy: it deletes unregistered-agent runs and all but one baseline per (project, branch), which the old schema can't hold.
- `pnpm verify` runs unit and integration tests in one pytest run with coverage tracing; the integration tests dominate its ~17 minutes.
- The `/shared/{token}` public view omits per-attempt trace steps (tool-call arguments, message-by-message detail) by design (ADR 0018); revisit if a real use case needs the full trace in a public link.
