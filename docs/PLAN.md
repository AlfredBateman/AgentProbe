# AgentProbe build plan

Source of truth for scope: [SPEC.md](../SPEC.md). UI: [DESIGN.md](../DESIGN.md). Rules: [CLAUDE.md](../CLAUDE.md). Status: [PROGRESS.md](PROGRESS.md).

## 1. Build order

The order you asked for was A → F. I suggested four changes, marked ★. **Approved 2026-09-25 (Q6)**, with one added requirement: `packages/core` must contain exactly one implementation of how a run executes (`execute_attempt`, `finalize_run`, `run_suite`); both the CLI's local run (D1.1) and the server runner (B2.3) call it directly and never reimplement it. B1.7 below carries this requirement.

- ★ **Minimal CI moves into Phase A.** Two reasons:
  - CLAUDE.md says red CI blocks "done".
  - `redis` tests can only run in CI, since Docker isn't available locally.

  Docker images, deploy and the dogfood Action stay in F.
- ★ **B is split into B1 (pure engine in `packages/core`) and B2 (server runner).** The CLI's local `run` (D1) sits between them. This gives an end-to-end vertical slice (YAML → agent → judges → pass rates → exit code) with no database, early.
- ★ **Golden tests move from C to the end of B1.** They're the proof that the engine detects anything at all, and they need only the demo agents and judges.
- ★ **The CLI is split into D1 (local run) and D2 (push/compare/baseline).** D2 needs the B2 API.

Every task ends with its gate green, PROGRESS.md updated, and a commit that's pushed.

### Phase A: foundation
Gate: `pnpm verify`, plus CI green.

| # | Task | Done when |
|---|---|---|
| A1 | CI workflow: `pnpm check`, then integration and redis tests. Uses Postgres+pgvector and Redis service containers. | PR run green |
| A2 | SQLAlchemy 2 async + psycopg 3, Alembic, and a settings module (pydantic-settings) | `pnpm db:migrate` works against a Neon branch |
| A3 | Schema migration for all tables in SPEC §7, with the approved changes in §3 below. Adds the `vector` extension. | Migration runs up and down on the test branch |
| A4 | Users, register/login/logout, and a JWT in an httpOnly cookie. Signup is gated by an allowlist. | Integration tests cover the happy path, a wrong password, and an email not on the allowlist |
| A5 | Projects CRUD, scoped to the owner. Project API keys: created, hashed, listed, revoked. Bearer auth. | Tests show user A can't read project B |

### Phase B1: core engine (`packages/core`, no DB)
Gate: `pnpm check`.

| # | Task | Done when |
|---|---|---|
| B1.1 | Suite YAML schema (pydantic) with size limits and the extensions in §2 (#10–13) | Unit tests on valid and invalid suites |
| B1.2 | LLM layer: role → model config, mock provider (deterministic), LiteLLM provider behind `RUN_LIVE=1`, budget guard | Mock is the default; a budget overrun raises; one `live` test |
| B1.3 | Demo agents: support-bot (tools), rag-bot, vulnerable-bot. Scripted mock mode, planted flaws with canary tokens. | Each serves HTTP locally |
| B1.4 | HTTP adapter: request template, dotted-path response mapping, timeouts, retries/backoff, SSRF guard | Unit tests, including private-IP blocking |
| B1.5 | Rule judges (all 10 in SPEC §4.5), `llm_rubric` (structured JSON verdict), consistency judge | Unit test per judge |
| B1.6 | Statistics: labels, suite CI, regression tests (§2 #9) + ADR | Property and known-value tests |
| B1.7 | `execute_attempt` / `finalize_run` / `run_suite`: the single implementation of how a run executes, with a concurrent multi-attempt run loop (asyncio semaphore). This is the **only** place run logic lives — the CLI (D1.1) and the server runner (B2.3) both call it, neither reimplements it. | Unit tests with a fake adapter; D1.1 and B2.3 both import it (checked by an ADR-referencing comment, not a duplicate loop) |
| B1.8 | Golden tests: vulnerable-bot's planted flaws are all detected in mock mode | Test asserts "X of Y planted flaws detected" |
| B1.9 | Coverage gate `--cov-fail-under=80` on core + api | `pnpm check` enforces it |

### Phase D1: CLI local run
Gate: `pnpm check`.

| # | Task | Done when |
|---|---|---|
| D1.1 | Typer app: `init`, `run suite.yaml`, `--fail-under`. The local run store is `.agentprobe/runs/`. | Exit codes tested; demo run works end to end |

### Phase B2: server runner and results API
Gate: `pnpm verify`, plus CI green.

| # | Task | Done when |
|---|---|---|
| B2.1 | Agents CRUD, including `secret_ref` storage. **Blocked on Q1.** | Secrets never returned or logged (tested) |
| B2.2 | Suites: create and `PUT` with immutable versioned case rows | A version bump keeps old runs readable |
| B2.3 | Queue: `QUEUE_BACKEND=inline\|arq`. Worker runs the core executor and persists results, traces and judgments. | Inline in `verify`, arq in CI (`redis`) |
| B2.4 | Runs API: start, status/summary, results, trace, `GET /runs/{id}/stream` (SSE) | Integration tests |
| B2.5 | Ingest (`POST /projects/{id}/runs:ingest`), baselines (set and get), compare endpoint | Integration tests |
| B2.6 | Export JSON/HTML (escaped), share links | An XSS payload in agent output is rendered inert (test) |

### Phase D2: CLI remote features
Gate: `pnpm verify`.

| # | Task | Done when |
|---|---|---|
| D2.1 | `--push`, `compare <a> <b>` (local or remote IDs), `--baseline <branch>` | Exit code is non-zero on regression (tested) |

### Phase C: security and AI features
Gate: `pnpm check` / `pnpm verify`.

| # | Task | Done when |
|---|---|---|
| C1 | Attack library: 8 categories from SPEC §4.4, parameterized templates, default expectations | Unit tests; golden tests extended |
| C2 | LLM mutator (seeded, budget-guarded) | Mock-mode determinism test |
| C3 | MCP adapter: list tools, `call:` cases, tool-description injection scan | Test against a bundled demo MCP server |
| C4 | Failure clustering: embeddings (768-d), clustering, LLM cluster summaries, `findings` API | Mock-mode test clusters planted failure groups |

### Phase E: dashboard (Next.js)
Gate: `pnpm check` + Playwright screenshots at 1440/810/390, compared against DESIGN.md.

| # | Task |
|---|---|
| E0 | ADR: dashboard adaptations of DESIGN.md (see §4). Base components: pill buttons, cards, inputs, badges. |
| E1 | Login/register, projects list, `/api/*` rewrite to FastAPI |
| E2 | Project overview (pass-rate and cost trend charts, latest runs) |
| E3 | Agents (add/edit, test connection), Suites (YAML editor with validation, case list) |
| E4 | Run detail (live SSE progress, per-case table, flaky badges, filters) |
| E5 | Trace viewer (CSS timeline, inline verdicts, side-by-side attempts) |
| E6 | Compare runs, Findings, Settings (API keys, read-only model config) |
| E7 | Playwright e2e: register → add agent → run suite → view trace → compare runs |

### Phase F: ship
| # | Task |
|---|---|
| F1 | GitHub Action (`action/`): runs the CLI, posts or updates the PR comment, fails on regression or threshold |
| F2 | Dogfood: AgentProbe's own CI runs the Action against the demo agents |
| F3 | Dockerfiles + `docker-compose.yml`; CI builds the images and smoke-tests compose |
| F4 | Deploy (web on Vercel; API + worker per Q2; Neon; Upstash). `deploy.yml` runs migrations on merge. |
| F5 | Hardening: rate limiting, security headers, dependency audit, security review |
| F6 | README: architecture, screenshots, measured metrics (SPEC §15), quick start. Script that measures the false-alert reduction. |

## 2. Ambiguities and contradictions in SPEC.md

Legend:
- **Approved**: you decided it (2026-09-24 or 2026-09-25).
- **Deferred**: intentionally postponed to a later phase; see the note.
- **Decided**: low impact; I'll record an ADR when the phase starts.

| # | Issue | Resolution | Status |
|---|---|---|---|
| 1 | `PUT /suites/{id}` rewrites `test_cases`, but `run_results.case_id` points at them, so editing a suite corrupts history. | Case rows are immutable per version. Add `test_cases.suite_version` and `runs.suite_version`, unique on (suite_id, suite_version, case_key). Runs compare across versions by `case_key`. | Approved |
| 2 | `--push` exists but there's no endpoint that accepts a locally executed run. The CLI and Action must execute locally anyway, because the agent is often on localhost in the user's CI. `/ci/report` is undefined. | `POST /projects/{id}/runs:ingest` (API key) upserts the agent and suite by name and stores the results. `GET /projects/{id}/baselines/{branch}`. `POST /ci/report` returns the verdict + PR-comment markdown. The Action posts the comment itself with `GITHUB_TOKEN`, so the API never holds GitHub tokens. | Approved |
| 3 | The auth mechanism is only "JWT/session". Web (Vercel) and API (Render) are cross-site. | Next.js rewrites `/api/*` to FastAPI (same origin). The API sets a short-lived JWT in an httpOnly, Secure, SameSite=Lax cookie. Mutations require a JSON content type (CSRF). CLI/CI use project API keys (`ap_…`, stored as SHA-256) as Bearer tokens. **Refined by [ADR 0009](decisions/0009-session-scheme.md):** a 15-minute access cookie, plus a rotating, hashed refresh cookie with reuse detection. Cookie mutations must also carry `Origin: WEB_ORIGIN`. An SSE stream-token fallback is designed for B2.4. | Approved |
| 4 | On a public deployment, anyone who registers spends the owner's LLM quota. Settings mentions "provider config", but there's no table for it. | Signup allowlist (`SIGNUP_ALLOWED_EMAILS`). The server key is used only through the budget guard (per-run and per-day USD caps). The public sees the demo via read-only share links. No BYOK in v1; Settings shows model config read-only. | Approved |
| 5 | The consistency judge is per case, but `judgments.run_result_id` is per attempt. | `run_result_id` becomes nullable. Add `run_id` and `case_id`, with a check constraint that exactly one scope is set. | Approved |
| 6 | "Shareable read-only link" has no storage. | `runs.share_token_hash`. `POST /runs/{id}/share` returns the token once; `DELETE /runs/{id}/share`; public `GET /share/{token}`. | Approved |
| 7 | `agents.secret_ref` doesn't say what it references. | A separate `secrets` table (id, project_id, ciphertext, created_at); `secret_ref` is the id of its row. Fernet encryption, key from `ENCRYPTION_KEY`, write-only, never returned or logged. See [ADR 0003](decisions/0003-secret-storage.md). | Approved |
| 8 | Two costs are implied: the agent's own tokens/cost, and AgentProbe's judge spend. `runs.model` is also unclear. | Add `runs.judge_cost_usd`. `total_cost`/`total_tokens` are the agent's, as reported through response mapping, and nullable. `runs.model` is a user-supplied label for the agent's model (A/B compare). | Approved |
| 9 | The statistics behind "statistically meaningful" aren't specified. | See the list after this table. Approved as proposed. Every threshold (α, `min_drop`, bootstrap/permutation iteration counts) is configurable via the suite YAML and CLI flags, not hardcoded, and the small-N limitation is documented prominently in `--help` and the docs. See [ADR 0006](decisions/0006-statistics-methodology.md). | Approved |
| 10 | `attack:` in the example is only a label, but §4.4 promises parameterized generators. | `attack` + `input` is a labelled literal case. `attack` without `input` expands library templates: `variants: N`, `mutate: true` for LLM variants, deterministic ids `<id>#<n>`, per-category default expectations that `expect` can override. | Decided |
| 11 | Indirect injection needs injected documents, but an HTTP black box can't receive them. | An optional case field `context:` (documents) is exposed to the request template. The demo support bot also has a planted malicious tool output. | Decided |
| 12 | The HTTP request/response mapping is unspecified, and tool-call judges need to see tool calls. | The request is a JSON template with `{{input}}` / `{{context}}`. The response uses dotted paths for `output`, `tool_calls`, `steps`, `usage`. Tool judges require the agent to report its calls; this is documented. | Decided |
| 13 | An MCP server has no chat "input". | MCP cases use `call: {tool, arguments}`, and judges run on the tool result. Plus an automatic scan of tool descriptions for injected instructions. | Decided |
| 14 | `adapter_type` includes `python`, but the Python adapter is CLI-only. | Allowed on ingested runs only. The server refuses to execute it. | Decided |
| 15 | Arq or Celery. | Arq (async-native, light). `QUEUE_BACKEND=inline\|arq`: inline locally, arq in CI and prod. | Decided |
| 16 | SSE or WebSocket. | SSE: one-way and cookie-friendly. It polls DB state, so inline and arq behave the same. | Decided |
| 17 | Integration tests "via Docker Compose" aren't possible without local Docker. | Locally: a Neon test branch (`pnpm verify`). CI: service containers. `docker-compose.yml` is shipped for users and verified only in CI. | Decided |
| 18 | The DB driver is unspecified. Neon URLs carry `sslmode` / `channel_binding`, which asyncpg rejects. | psycopg 3 async (`postgresql+psycopg://`). | Decided |
| 19 | A pgvector column needs a fixed dimension, but the embedding model is configurable. | `EMBEDDING_DIM=768`. The embedding call requests 768 dimensions, and the mock embeds to 768. Changing it needs a migration. | Decided |
| 20 | Rate-limit storage isn't specified. | **Superseded by [ADR 0009](decisions/0009-session-scheme.md):** a `RateLimiter` token-bucket interface. In-memory by default (marked `ponytail:`); a Redis Lua implementation for multi-instance deployments. Limits are per API key, and per IP on register/login. Over the limit: 429 with `Retry-After`. | Decided |
| 21 | 80% coverage on "backend core": scope and timing. | `--cov-fail-under=80` on `packages/core` + `apps/api`, enforced from B1.9 (not on the empty scaffold). | Decided |
| 22 | React Flow for the trace timeline. | A trace is an ordered list, so React Flow is dropped for plain semantic HTML/CSS (E5). See [ADR 0005](decisions/0005-trace-timeline-no-react-flow.md). | Approved |
| 23 | Mock LLM behaviour isn't defined. | A pure function of (role, prompt): a fixture table matched by substring, otherwise a hash-seeded default. Demo agents have a scripted mock mode, so planted flaws are deterministic. Golden tests rely on canary tokens and rule judges, so they're meaningful offline. | Decided |
| 24 | Hosting cost: Render's free tier has no background workers. | Deferred to F4 (deployment phase): decide after checking then-current free-tier terms. What's fixed now is that the worker sits behind the `QueueBackend` interface (item 15) with `inline` as the local default, so the hosting choice doesn't leak into `packages/core` or `apps/api` business logic. | Deferred to F4 |
| 25 | The Python version was 3.11+, and the repo layout put the engine inside `apps/api`. | Python 3.12. The engine lives in `packages/core` ([ADR 0001](decisions/0001-core-package.md)). | Decided |

### #9: statistics
- **Attempts.** An attempt passes when every expectation passes. `error` (a timeout or adapter failure after retries) counts as not passed and is shown separately.
- **Case labels.** `stable-pass` when k = n, `stable-fail` when k = 0, `flaky` otherwise.
- **Suite pass rate.** The mean of case pass rates. Its 95% CI comes from a seeded case-level cluster bootstrap. Wilson on pooled attempts would be too narrow, because attempts within a case aren't independent.
- **Per-case regression.** One-sided Fisher exact test, Holm-corrected, α = 0.05.
- **Suite regression.** One-sided paired sign-flip permutation test on per-case deltas: exact up to 20 cases, otherwise 10k seeded draws.
- **When a regression is flagged.** Only when the result is significant *and* the drop is at least `min_drop` = 0.05.
- **`--fail-under`.** Applies to the point estimate.
- **Implementation.** stdlib only (`math.comb`, `random.Random(seed)`).
- **Known limit.** At 5 runs, a single case reaches significance only on large drops (5/5 → 1/5).

## 3. Data model as approved (changes to SPEC §7)
- `test_cases`: add `suite_version`; unique (suite_id, suite_version, case_key); add `context` JSONB and `call` JSONB (MCP).
- `runs`: add `suite_version`, `judge_cost_usd`, `share_token_hash`. `model` is a user label.
- `judgments`: `run_result_id` becomes nullable; add `run_id` and `case_id`, with a check that exactly one scope is set.
- **New table `secrets`**: id, project_id, ciphertext (Fernet, key from `ENCRYPTION_KEY`), created_at. Write-only via the API; never returned or logged. `agents.secret_ref` is the id of a row here. See [ADR 0003](decisions/0003-secret-storage.md).
- `findings.embedding`: `vector(EMBEDDING_DIM)`, default 768.
- **Added in A3** ([ADR 0007](decisions/0007-data-model-additions.md)):
  - `runs`: `config_snapshot`, `error`, `mock_mode`, `pr_number`, `share_expires_at`, `created_at`.
  - `run_results`: unique (run_id, case_id, attempt).
  - New table `run_case_summaries`.
  - Every FK is covered by an index, plus `runs (suite_id, created_at)`.

A1–A3 are done (2026-09-25).

A4–A5 are done (2026-09-25). `refresh_tokens` table and `api_keys.last4 / created_at / revoked_at` added in migration 0002 ([ADR 0009](decisions/0009-session-scheme.md)).

API additions: `POST /projects/{id}/runs:ingest`, `GET /projects/{id}/baselines/{branch}`, `POST|DELETE /runs/{id}/share`, `GET /share/{token}`, `POST /auth/logout`.

## 4. DESIGN.md vs. a dashboard (ADR at E0)
DESIGN.md describes a marketing site. These are the proposed adaptations:
- **Type sizes.** Page titles use display-md/lg. The 85–110px sizes are for marketing only.
- **Fonts. Approved (Q3).** GT Walsheim is proprietary. **Geist** substitutes for display, **Geist Mono** for monospace/code (YAML editor, trace payloads), **Inter Variable** stays for body with the documented cv/ss OpenType features. See [ADR 0004](decisions/0004-font-substitution.md).
- **Status colors.** Pass/fail/flaky need danger and warning colors. They'll be added as glyph/badge-only tokens, the same way `semantic-success` is used; never as surfaces.
- **Charts.** Series use ink, ink-muted and the gradient anchors. `accent-blue` stays reserved for links, focus and selection.
- **Screenshot widths.** 1440 / 810 / 390. The "Mobile-XS 98px" breakpoint is treated as a typo.
- **Trace timeline. Approved (Q4).** Plain semantic HTML/CSS, not React Flow — see item 22 above and [ADR 0005](decisions/0005-trace-timeline-no-react-flow.md).

## 5. Decisions (resolved 2026-09-25)
All six blocking questions are answered. Nothing in this section is open.

1. **Q1 — `agents.secret_ref`.** A separate `secrets` table (id, project_id, ciphertext, created_at); `secret_ref` is that row's id. [ADR 0003](decisions/0003-secret-storage.md). Unblocks B2.1.
2. **Q2 — hosting for the API and worker.** Deferred to F4, deliberately: decide after checking free-tier terms current at deploy time. The one fixed requirement, already true of the design (item 15), is that the worker stays behind the `QueueBackend` interface with `inline` as the local default — the hosting choice must never leak into `packages/core` or `apps/api` business logic.
3. **Q3 — display font substitute.** Geist for display, Geist Mono for monospace, Inter Variable for body. [ADR 0004](decisions/0004-font-substitution.md).
4. **Q4 — React Flow.** Dropped. Plain semantic HTML/CSS timeline (E5). Revisit only if branching multi-agent traces are added. [ADR 0005](decisions/0005-trace-timeline-no-react-flow.md).
5. **Q5 — statistics method (#9).** Approved as proposed: Fisher exact per case with Holm correction, a paired sign-flip permutation test at suite level, a case-level bootstrap for the CI, α = 0.05, `min_drop` = 0.05. All of these are configurable via the suite YAML and CLI flags, not hardcoded, and the small-N power limitation is documented prominently (CLI `--help` and the docs). [ADR 0006](decisions/0006-statistics-methodology.md).
6. **Q6 — build-order changes (★ in §1).** Approved, with one added requirement: `packages/core` holds exactly one implementation of how a run executes (`execute_attempt` / `finalize_run` / `run_suite`); the CLI's local run and the server runner both call it, neither reimplements it. Carried into B1.7 above.
