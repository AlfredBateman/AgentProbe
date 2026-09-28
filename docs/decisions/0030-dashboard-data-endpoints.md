# 0030: Dashboard data endpoints (suite detail, project runs, agent test-connection, structured validation issues)

Status: accepted (2026-09-28). Backend groundwork for PLAN.md's E2 (project overview) and E3 (agents, suites).

## Context
E2/E3's dashboard pages need three things the API didn't expose: a way to read a suite's saved YAML back (the editor has to load it before it can edit it), a way to list a project's runs (the overview page's pass-rate/cost/latency trend charts and latest-runs table), and an HTTP route for the `test_connection()` methods `HttpAdapter`/`McpAdapter` already have in `packages/core` (the agents page's "Test connection" button). Suite validation errors also needed to become locatable in an editor, not just readable in a terminal.

## Decision

### 1. `GET /suites/{suite_id}`
Returns `SuiteDetailOut` (`SuiteOut` plus `yaml: str`, the stored `yaml_source`). Ownership via the existing `owned_suite`.

### 2. `GET /projects/{project_id}/runs`
Paginated (`limit` 1–200 default 50, `offset`), optionally filtered by `suite_id`, newest first. Returns `RunListOut`: the fields already on `Run`, plus the suite's and agent's *current* names (joined, not the historical `config_snapshot` values — this is a live listing, not an audit trail) and a new **`mean_latency_ms`**, computed at read time as the attempts-weighted average of `run_case_summaries.mean_latency_ms` across the run's cases. It isn't a stored column: `runs` already carries `pass_rate`/`total_cost`/etc. as finalize-time aggregates, but latency was never rolled up to run level, and computing it from the existing per-case rows avoids adding one.

### 3. Suite JSON Schema: a build-time export, not an endpoint
`packages/core.suite.suite_json_schema()` already existed but was never reachable from the web app. It's static — it doesn't depend on any request or database state — so it's cheaper to export once at build time than to add an authenticated endpoint the editor calls on every load. `scripts/export_suite_schema.py` writes `apps/web/src/lib/api/suite-schema.json` (the JSON Schema plus the sorted `ATTACKS` id/category registry, for the same reason: also static). `packages/core/tests/suite/test_export_suite_schema.py` fails if the committed file drifts from `packages/core`, the same freshness-gate pattern `test_openapi_schema.py` already uses for the OpenAPI client.

### 4. Suite validation: structured, locatable issues
`SuiteParseError.issues` changes from `list[str]` to `list[SuiteIssue]` (`packages/core/src/agentprobe_core/suite/parser.py`): `{message, path, line, col}`.
- **YAML syntax errors** always carry `line`/`col` (from PyYAML's `problem_mark`; `path` is `None`).
- **Schema violations** (`pydantic.ValidationError`) get a dotted `path` (the error's `loc`) always, and best-effort `line`/`col`: the YAML is parsed a second way with `yaml.compose()` (stdlib PyYAML, no new dependency) into a node tree with source positions, and the error's `loc` is walked against it. A `loc` that doesn't resolve to a node (an empty loc, an out-of-range index, a key that isn't really there) falls back to `line=None, col=None` rather than raising — locating an issue is a nicety, never a reason to fail validation.
- Every place `SuiteParseError` surfaces (`POST /suites/validate`, and the 422 `details` on suite create/update, `POST /suites/{id}/runs`, and `POST /ci/report`) carries the same structured shape now, not just `validate`.

### 5. Agent connection test
`POST /agents/{agent_id}/test` (a saved agent: decrypts its stored secret, same as a real run) and `POST /projects/{project_id}/agents/test` (a not-yet-saved draft: the same `AgentConfig`/`AuthHeader` body shape as create, used once and never persisted or logged). Both build an adapter with the existing `build_adapter` and call its existing `test_connection()` — "one probe request, no retries," per its own docstring — and return `{success, message}`. `message` is always the adapter's own error text, which is already sanitized (ADR 0012: a blocked or failed target's user-facing error never includes a resolved address); no new sanitization was added.

## Consequences
- No new stored data: `mean_latency_ms` and the resolved agent/suite names are computed at read time, not written anywhere.
- `SuiteParseError.issues`'s type change is a breaking shape change, deliberately: every caller (`packages/cli`, `apps/api/suites.py|runs.py|ci.py`) and every test asserting on `.issues` was updated in the same change.
- The suite schema/attack registry is a committed static file, like `openapi.json` — it goes stale only if someone edits `packages/core`'s suite schema and forgets to re-run the export script, and the new test catches that.
- Both test-connection routes reuse `agentprobe_api.runstore.close_adapter` for cleanup rather than duplicating it.
- Known limit, matching an existing one: `POST /suites/{id}/runs` still only runs `http` agents (ADR 0012/0023's existing restriction), so the run dialog (E2/E3) can only offer http agents — this ADR doesn't change that.
