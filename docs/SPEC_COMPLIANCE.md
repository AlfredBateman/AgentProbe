# SPEC compliance

Every feature in SPEC.md §4 (core features), §8 (API), §9 (dashboard) and §14 (MVP and
should-have tiers), with its status and where it lives. §10 (security) maps each bullet to
the tests that prove it. Checked 2026-10-03, against `main` plus the review pass that wrote
this file.

Status: **done**, **partial** (works, with a stated gap), **missing**. A scope cut the user
decided is marked as such, with its ADR.

## §14 scope tiers

### Must-have (MVP): no item missing

| Item | Status | Where |
|---|---|---|
| YAML suites | done | `packages/core/src/agentprobe_core/suite/` (schema, safe parser), `suites/examples/` |
| HTTP adapter | done | `packages/core/src/agentprobe_core/adapters/http.py`, SSRF guard `adapters/ssrf.py` |
| Runner with repeated runs | done | `packages/core/src/agentprobe_core/runner.py` (`run_suite`), server queue `apps/api/src/agentprobe_api/queue.py` |
| Rule-based judges + LLM-as-judge | done | `packages/core/src/agentprobe_core/judges/rules.py`, `judges/llm_rubric.py` |
| Attack library (injection, jailbreak, system-prompt leak, tool misuse) | done, as scoped by ADR 0027 | Registry of 15 ids in 6 categories: `packages/core/src/agentprobe_core/suite/attacks.py`. Labelled cases per MVP category: `suites/examples/smoke.yaml` (injection, leak), `rag-safety.yaml` (indirect injection), `mcp-safety.yaml` (argument tampering), `support-agent-safety.yaml` (injection, tool misuse), `jailbreak-extraction.yaml` (jailbreak, extraction; added in this pass). Payloads are author-written; generators were cut by user decision ([ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md)). |
| Trace storage + basic trace viewer | done | `traces` table (`apps/api/src/agentprobe_api/models.py`), `GET /results/{id}/trace` (`results.py`), `apps/web/src/components/trace/timeline.tsx` |
| Run results page with pass rate and flaky labels | done | `apps/web/src/app/(app)/projects/[projectId]/runs/[runId]/page.tsx`, `components/run/case-table.tsx` |
| CLI with `run` and `--fail-under` | done | `packages/cli/src/agentprobe/main.py` |
| Regression compare | done | `packages/core/src/agentprobe_core/stats/regression.py`, `GET /runs/compare`, CLI `compare`, compare page |
| GitHub Action with PR comment | done | `action/action.yml`, `action/format_comment.py`, `action/post_comment.py` |
| Docker Compose, CI, one live deployment | done | `docker-compose.yml`, `.github/workflows/ci.yml`, `deploy.yml`; live at https://agent-probe-umber.vercel.app |
| Demo agents with planted vulnerabilities | done | `demo-agents/`, manifest `demo-agents/vulnerabilities.json` (9 of 9 detected, `demo-agents/tests/test_golden.py`) |

### Should-have

| Item | Status | Where |
|---|---|---|
| MCP adapter | done | `packages/core/src/agentprobe_core/adapters/mcp.py`, `mcp_ssrf.py` |
| Failure clustering with pgvector | done | `packages/core/src/agentprobe_core/findings.py`, `apps/api/src/agentprobe_api/findings.py` (embeddings in a pgvector column) |
| Attack mutator (LLM-generated variants) | missing: **cut by user decision** | [ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md) (2026-09-27) |
| Cost and latency tracking charts | done | `apps/web/src/components/run/trend-charts.tsx` on the project overview ([ADR 0037](decisions/0037-project-overview-and-runs-page.md)) |
| Read-only shareable run link | done | `apps/api/src/agentprobe_api/share.py`, `apps/web/src/app/shared/[token]/page.tsx` |

## §4 core features

| Feature | Status | Where / gap |
|---|---|---|
| 4.1 YAML suites | done | `suite/schema.py`, `suite/parser.py` (safe load, no anchors, 256 KB, 500 cases) |
| 4.2 HTTP adapter (mapping, encrypted auth header) | done | `adapters/http.py`; header encrypted in `secrets` (`apps/api/src/agentprobe_api/crypto.py`, [ADR 0003](decisions/0003-secret-storage.md)) |
| 4.2 MCP adapter | done | `adapters/mcp.py` (Streamable HTTP on the server, stdio in the CLI) |
| 4.2 Python adapter (CLI only) | done | `adapters/python.py`; refused on the server by construction |
| 4.2 Demo agents (2-3) | done | `demo-agents/src/agentprobe_demo_agents/` (support v1/v2, rag, vulnerable, MCP tools) |
| 4.3 Concurrent worker queue | done | `runner.py` (bounded TaskGroup workers), `queue.py` (inline / Redis + Taskiq) |
| 4.3 `runs_per_case` repeats | done | `runner.plan_attempts` |
| 4.3 Full trace per attempt (steps, tool calls, latency, tokens, cost) | done | `runner.execute_attempt`, `adapters/types.py` |
| 4.3 Timeouts, retries, provider rate limits | done | `adapters/http.py` (timeouts, retry on connect/429/5xx), `llm/limits.py` (RPM/RPD, backoff) |
| 4.4 Direct / indirect injection, jailbreaks, extraction, leakage, tool misuse, scope drift | done, as labelled cases | `suite/attacks.py`, `suites/examples/*.yaml` |
| 4.4 Obfuscation (base64, leetspeak, Hinglish) | missing: **cut by user decision** | [ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md) |
| 4.4 Parameterized generators and LLM mutator | missing: **cut by user decision** | [ADR 0027](decisions/0027-attack-ids-label-author-written-cases.md) |
| 4.5 Rule judges (all 10) | done | `judges/rules.py` |
| 4.5 LLM-as-judge (structured verdict) | done | `judges/llm_rubric.py` (delimited untrusted text, schema verdict, majority vote) |
| 4.5 Consistency judge | done | `judges/consistency.py` |
| 4.5 Judge results stored with reasoning | done | `judgments` table, trace and share views |
| 4.6 Per-case pass rate, stable/flaky labels, suite CI | done | `stats/summary.py` |
| 4.6 Regression only when statistically meaningful | done | `stats/significance.py`, `stats/regression.py` ([ADR 0014](decisions/0014-statistics-implementation.md)) |
| 4.7 Compare any two runs; status, score, cost and latency deltas; newly failing/passing/flaky | done | `stats/regression.py`, `results.py` (`/runs/compare`), compare page |
| 4.8 Failure clustering with LLM summaries and suggested fixes | done | `findings.py` (core and api), findings page |
| 4.9 Trace timeline, inline verdicts, side-by-side compare | done | `components/trace/timeline.tsx`, results page `?compare=` ([ADR 0031](decisions/0031-run-detail-and-trace-viewer.md)) |
| 4.10 CLI `init`, `run`, `--push`, `compare`, `--fail-under`, `--baseline`; exit codes | done | `packages/cli/src/agentprobe/main.py`, `push.py` |
| 4.10 `pip install agentprobe` | **partial** | Not published. The PyPI name `agentprobe` belongs to an unrelated project, so the docs install from this repository by git URL (`packages/cli/README.md`) and the Action installs from its own source. Publishing needs a name decision (open item 1). |
| 4.11 Action: runs the suite, PR comment (pass rate, regressions, clusters, link), fails the check | done | `action/`, dogfood `.github/workflows/agentprobe-dogfood.yml` |
| 4.12 HTML/JSON export, shareable read-only link | done | `GET /runs/{id}/export` (`runs.py`, `htmlexport.py`), `share.py` |

## §8 API endpoints

All present (from `apps/web/src/lib/api/openapi.json`, which a test keeps in sync with the app).

| Endpoint | Status | Where |
|---|---|---|
| `POST /auth/register`, `POST /auth/login` | done | `auth.py` (plus `/auth/refresh`, `/auth/logout`, `/auth/me`) |
| `GET /projects`, `POST /projects`, `GET /projects/{id}` | done | `projects.py` |
| `POST/GET /projects/{id}/agents` | done | `agents.py` |
| `POST/GET /projects/{id}/suites` | done | `suites.py` |
| `PUT /suites/{id}` | done | `suites.py` (new version per changed YAML) |
| `POST /suites/{id}/runs` | done | `runs.py` |
| `GET /runs/{id}` | done | `runs.py` |
| `GET /runs/{id}/results` | done | `results.py` |
| `GET /results/{id}/trace` | done | `results.py` |
| `GET /runs/{id}/findings` | done | `findings.py` |
| `GET /runs/compare?a=&b=` | done | `results.py` |
| `POST /projects/{id}/baseline` | done | `baselines.py` |
| `POST /ci/report` | done | `ci.py` |
| `GET /runs/{id}/export?format=json\|html` | done | `runs.py`, `htmlexport.py` |
| `GET /runs/{id}/stream` (SSE) | done | `runs.py` (with the stream-token fallback, ADR 0009 §5) |

## §9 dashboard pages

All under `apps/web/src/app/`.

| Page | Status | Where |
|---|---|---|
| 1. Login / Register | done | `login/page.tsx`, `register/page.tsx` |
| 2. Projects list | done | `(app)/projects/page.tsx` |
| 3. Project overview: pass-rate trend, latest runs, cost trend | done | `(app)/projects/[projectId]/page.tsx` (plus latency trend and the Runs page) |
| 4. Agents: add/edit, adapters, test connection | done | `(app)/projects/[projectId]/agents/page.tsx` |
| 5. Suites: YAML editor with validation, case list | done | `(app)/projects/[projectId]/suites/page.tsx`, `suites/[suiteId]/page.tsx` |
| 6. Run detail: live progress, per-case table, flaky badge, filters | done | `(app)/projects/[projectId]/runs/[runId]/page.tsx` |
| 7. Trace viewer: timeline, inline verdicts | done | `runs/[runId]/results/[resultId]/page.tsx` |
| 8. Compare runs | done | `runs/[runId]/compare/page.tsx` |
| 9. Findings | done | `runs/[runId]/findings/page.tsx` |
| 10. Settings: API keys, model/provider config | done | `(app)/projects/[projectId]/settings/page.tsx`; model config is read-only by approved decision (PLAN.md §2 #4: no BYOK in v1) |

## §10 security considerations

Every bullet has a test that names what it proves. "Added" marks a test written in this pass
because none existed.

| Bullet | Tests |
|---|---|
| Agent auth headers and provider keys stored encrypted, never logged | `apps/api/tests/test_agents.py::test_auth_header_is_encrypted_and_never_returned`, `test_crypto.py::test_ciphertext_is_randomized_and_opaque`, `test_log_redaction.py::test_secrets_never_reach_logs` (DEBUG + SQL logging, includes the encrypted header's plaintext). Provider keys live only in the environment, are never stored, and are cut out of provider error text (`packages/core/src/agentprobe_core/llm/live.py`). |
| SSRF protection on the HTTP adapter | `packages/core/tests/adapters/test_ssrf.py` (every blocked class, DNS rebinding, redirects, the opt-in truth table), `test_allowlisted_host_still_resolves_validates_and_pins`, MCP's `test_mcp.py`, e2e `08-ssrf-blocked-agent.spec.ts` |
| Rate limiting per API key | `apps/api/tests/test_projects.py::test_api_keys_are_rate_limited` (per key, not global), `test_ratelimit.py` (both backends). Also per IP on auth (`test_auth.py::test_auth_endpoints_are_rate_limited_per_ip`) and, added, per account on connection tests (`test_limits.py::test_connection_tests_are_limited_per_account`) |
| Attack payloads run only against agents the user registered | **Added**: `apps/api/tests/test_spec10_security.py::test_spec10_runs_target_only_the_suites_own_registered_agent`. Also `test_idor.py` (no run on another user's suite) and `test_python_adapter_isolation.py` |
| YAML schema-checked and size-limited | `packages/core/tests/suite/test_parser.py::test_oversized_file_rejected`, `test_anchor_alias_bomb_rejected`, `test_schema.py`. **Added**: `test_spec10_security.py::test_spec10_oversized_suite_yaml_is_rejected_and_nothing_saved` (through the API) and `test_request_bodies_over_the_cap_are_refused_before_reading` (10 MiB body cap, declared or chunked) |
| Secrets never committed; `.env.example` provided | **Added**: `test_spec10_security.py::test_spec10_env_example_documents_every_variable_the_code_reads`, `test_spec10_env_example_lists_nothing_the_code_ignores`, `test_spec10_env_example_holds_no_real_secret`. CI's `audit` job runs gitleaks over the full history. Found and fixed: `AGENT_MODE`, `FLAKY_RATE`, `FLAKY_SEED` were undocumented; `RUNNER_CONCURRENCY` and `AGENTPROBE_PROJECT` were read by nothing. |

Beyond §10, this pass added or verified (all in [ADR 0039](decisions/0039-security-headers-csp-and-request-limits.md)):

| Guarantee | Tests |
|---|---|
| Security headers on every API response (CSP `default-src 'none'`, nosniff, `X-Frame-Options`, `Referrer-Policy`, HSTS) | `test_spec10_security.py::test_security_headers_are_on_every_response` |
| A nonce-based Content-Security-Policy on every web page, plus static headers | `apps/web/src/proxy.test.ts` (fresh nonce, no `unsafe-inline` script, framing and plugins blocked); `next.config.ts` |
| CORS locked: no route grants a cross-origin read except the token-authenticated SSE stream, to `WEB_ORIGIN` only | `test_spec10_security.py::test_cors_no_route_grants_cross_origin_reads`, `test_runs.py::test_stream_token_fallback` |
| CSRF: every cookie-authenticated mutation, the auth routes included, needs `Origin == WEB_ORIGIN` | `test_spec10_security.py::test_csrf_every_mutating_route_rejects_a_foreign_or_missing_origin` (enumerates the routes from the app, so a new route is covered automatically), `test_auth.py::test_cookie_mutations_require_web_origin` |
| XSS: trace viewer, HTML export, share page | `apps/web/src/components/trace/timeline.test.tsx` (untrusted content as literal text), `apps/api/tests/test_htmlexport.py::test_xss_html_export_escapes_every_untrusted_field` (added), `test_export.py::test_html_export_escapes_hostile_agent_output`, `apps/web/src/app/shared/[token]/page.test.tsx` (added), `apps/web/src/no-raw-html.test.ts` |

## F5 hardening (PLAN.md §1)

| Item | Status | Where |
|---|---|---|
| Rate limiting | done | per API key, per IP on auth and registration, per account on connection tests (`ratelimit.py`, `auth.py`, `agents.py`) |
| Security headers | done (this pass) | API `main.py` (`SECURITY_HEADERS`), web `src/proxy.ts` and `next.config.ts` |
| Request body cap | done (this pass) | `main.py` (`MAX_BODY_BYTES`, 10 MiB) |
| Dependency audit | done | CI `audit` job: pip-audit over every locked package, `pnpm audit` ([ADR 0034](decisions/0034-dependency-audits.md)) |
| Secret scanning | done (this pass) | CI `audit` job: gitleaks 8.30.1 over all history (checksum-pinned); known public dev values in `.gitleaksignore` |
| Public-abuse limits | done | signup caps, per-user caps, global live-LLM budget ([ADR 0035](decisions/0035-production-deploy-and-public-abuse-limits.md)), plus the connection-test limit (this pass) |
| Security review | done (this pass) | this file; PROGRESS.md 2026-10-03 |

## Open items for the user

1. **PyPI name.** `agentprobe` on PyPI is someone else's project (`nkkko/agentprobe`, 0.3.x). Until you choose a free name and publish, the CLI installs from this repository. The Action already does that by default, at the ref you pin.
2. **Attack mutator and obfuscation** are should-have/§4.4 items cut by your decision in ADR 0027. Listed so the cut stays visible.
3. **F4 follow-ups that need the Render dashboard**, unchanged: the `PROXY_SECRET` client-IP check, the memory graph around a deploy, `API_EXTRAS=live` as a build arg (ADR 0036 §Still unverified).
4. **Live detection run with Gemini**: deferred by your decision on 2026-10-03.
