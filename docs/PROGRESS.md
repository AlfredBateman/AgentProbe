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
  - [docs/metrics.md](metrics.md): the new honest headline is **70.6% → 2.3% false alarms, a 96.7% reduction**, with single-break detection going from 4.1% (Holm) to 100%. Holm and Tarone–Holm are shown side by side in every scenario. A null calibration grid separates the per-case family from the whole verdict. The simulation parameters were unchanged.
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

## Next
- B1.8: golden tests. Fill in `demo-agents/vulnerabilities.json` `suite_case_ids` (the smoke suite covers 5 of the 7 planted flaws; instruction injection and RAG indirect injection need cases with `context`).
- B2.3: the server runner calls `run_suite` with a DB-writing `on_result` and a status-driven `cancel` event (ADR 0016), and adds no run loop of its own.
- Decision needed (ADR 0014 §Verdict, docs/metrics.md): the whole verdict (per-case family + suite test) is bounded by 2·`alpha`, not `alpha`. It measures up to 6.5% on heavily flaky suites, while the per-case family stays at or below `alpha`. Option: split `alpha` between the two (for example `alpha`/2 each). At 5 runs a single break would still be flagged; at 3 runs it never could be.

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

- Statistics implementation ([ADR 0014](decisions/0014-statistics-implementation.md)):
  - The case is the resampling unit (within-case correlation).
  - A Wilson floor for degenerate bootstraps.
  - One-sided Fisher tests; a Tarone–Holm step-down per case (user decision), with worse and better as separate families. Thresholds are reported, not adjusted p-values.
  - Exact sign-flip by dynamic programming (exact beyond ADR 0006's 20 cases when cheap), with a Monte Carlo fallback.
  - Exact rational threshold comparisons.
  - One flagged case is a regression even when the suite drop is below `min_drop`. Regression wins the verdict. The per-case family is held at `alpha`; the whole verdict at 2·`alpha` (union bound).
  - Only shared cases are compared.
  - Cost deltas are per attempt.
- Regex judge ([ADR 0015](decisions/0015-regex-judge-hardening.md)): the `regex` package with a 0.25 s matching timeout; a stdlib-parser expansion bound (10,000 elements) before compiling; the output cap raised to 100,000. RE2 was considered and rejected: it has no lookarounds, backreferences or verbose mode, and logs parse errors to stderr.
- Run execution and CLI ([ADR 0016](decisions/0016-run-execution-and-local-cli.md)):
  - A judge `error` makes the attempt an `error`.
  - Only `unreachable` attempts are retried at run level.
  - Consistency is reported per case and doesn't change the pass counts.
  - The agent's cost is `None` without a configured price.
  - `--fail-under` defaults to 1.0. Exit precedence is 4 > 2 > 1.
  - The CLI grants the policy half of the private-target opt-in itself; the agent must still set `allow_private: true`.
  - Attack-only and `mutations` cases are refused up front until the attack library and the mutator exist.

## Known issues
- Statistics power (ADR 0014 §Power):
  - At 3 runs per case, a single break has p = 1/20 = `alpha` and is detected only 38.4% of the time (any other case able to reach `alpha` raises K). Use 5 or more runs.
  - A case that only turns flaky (5/5 → 3/5) is weak evidence at 5 runs.
- The whole verdict's false-alarm rate can exceed `alpha` on heavily flaky suites: up to 6.5% measured, 2·`alpha` bound. See Next.
- `test_family_wise_error.py` adds about 12 s to `pnpm check` (24 seeded cells × 1,000 trials).
- The regex judge blocks the event loop for up to 0.25 s per attempt when a pattern times out. A suite that times out everywhere costs that on every attempt. B1.7 did not add a run-level time budget; B2.3 should, or fail a pattern fast after its first timeout in a run.
- `agentprobe run` with `llm.provider: litellm` outside the repo root fails with exit 3 ("config/llm.yaml not found"): the live LLM config is read from `AGENTPROBE_CONFIG_DIR` (default `config/`). A pip-installed CLI needs the model/pricing config shipped as package data before live judging works outside the repo (F6).
- The CLI stops at the first infrastructure error (ADR 0016), but that first attempt still spends its full retry budget. On Windows a refused localhost connect takes about 2 s, so a down agent costs about 20 s before exit 4.
- The regex judge's compile-time guard relies on the stdlib parser (`re._parser`, private, no stubs) agreeing with `regex` on how repeats nest. The 10,000-element limit leaves 100× headroom for disagreement (ADR 0015).
- The suite CI under-covers with few cases: 87% at 10 cases vs 94% at 30 (percentile cluster bootstrap, ADR 0014).
- `pnpm verify` needs `TEST_DATABASE_URL`, `DATABASE_URL` and `ALLOW_DB_TESTS=1` (loaded from `.env`). Without them it refuses with exit code 2, which is intended. It takes about 2.5 min against Neon from here: each request costs 2–4 round trips of 80–140 ms (more on a bad network day). A Neon region closer to the developer would cut this proportionally.
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
- The daily quota file (`.agentprobe/llm-quota.json`) has no cross-process lock: concurrent processes can undercount by a few requests. Move the counters to Redis/Postgres with the multi-worker runner (B2.3).
- Free-tier RPM/RPD defaults (10/250) are placeholders: Google only shows the real per-model values in AI Studio. Set `LLM_RPM`/`LLM_RPD` in `.env` from https://aistudio.google.com/rate-limit.
