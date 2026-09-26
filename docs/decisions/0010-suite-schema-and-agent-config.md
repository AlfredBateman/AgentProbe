# 0010: Suite schema field names and agent config shape

Status: accepted (2026-09-24). HTTP agent config now lives in `packages/core`:
see [ADR 0012](0012-http-adapter-and-ssrf-guard.md).

## Context
Two low-impact gaps needed a concrete answer before B1.1 (suite YAML schema) and B2.1/B2.2
(agents and suites CRUD) could be implemented: SPEC.md §4.5 names the ten rule-based judges
but not their parameter fields, and SPEC.md §4.2/§7 says agent `config` is adapter-specific
JSONB but not its shape or how it's validated.

## Decision
- **Judge spec fields** (`packages/core`, `agentprobe_core.suite.judges`): `contains` takes
  `value` (singular); `contains_any`/`not_contains` take `values` (plural, matching the
  SPEC.md §4.1 example); `regex` takes `pattern` (+ optional `flags`); `json_schema` takes
  `schema` (aliased from the reserved attribute name `schema_`); `max_length` takes
  `max_chars`; `latency_under` takes `ms`; `tool_called`/`tool_not_called` take `tool`;
  `tool_args_match` takes `tool` + `args`; `llm_rubric` takes `rubric`; `consistency` takes
  an optional `min_agreement` (default 1.0). All twelve specs are a `Field(discriminator=
  "judge")` union with `extra="forbid"`, so an unknown judge type or field is a schema error,
  not a silent no-op.
- **Case fields**: `attack` (a registry id) and `attack_params` (dict) are separate, matching
  the user's B1.1 brief; PLAN.md §2 #10's `variants`/`mutate` expansion is Prompt 12's scope,
  not this one. `context` (not `fixtures`) is the field name for injected documents, matching
  the already-approved data model column (PLAN.md §2 #11, `test_cases.context`) and ADR 0007.
- **Attack registry** (`agentprobe_core.suite.attacks`): a module-level `set[str]` with
  `register_attack`/`is_registered_attack`. `prompt_injection.direct` and `tool_misuse` are
  pre-registered as placeholders so `suites/examples/support-agent-safety.yaml` parses before
  Prompt 12 fills the real generators.
- **Anchor/alias bombs**: rejected by scanning YAML tokens for `AliasToken`/`AnchorToken`
  before `yaml.safe_load` runs, rather than a custom `Loader` subclass. A suite file has no
  legitimate use for either, so this is a flat rejection, not a size-limited allowance.
- **Agent config** (`apps/api.agents`): a discriminated union (`http` | `mcp` | `python`) kept
  in `apps/api`, not `packages/core` — the HTTP adapter's real request/response templating is
  B1.4, not built yet, so this union only validates the *shape* the server stores and rejects
  (structurally invalid config, and `python` outright, per PLAN.md §2 #14). `url`/`server_url`
  use pydantic's `AnyHttpUrl` for format validation; the SSRF guard (private-IP blocking) is
  B1.4's runtime concern, not this storage-layer validation.
- **Secrets**: an agent's `auth_header: {name, value}` is JSON-encoded and encrypted with the
  existing `SecretBox` (ADR 0003) into a new `secrets` row; `agents.secret_ref` points at it.
  Replacing or clearing a secret orphans the old row rather than deleting it (`ponytail:`
  comment in `agents.py`), since stale ciphertext isn't a security or correctness problem by
  itself — a cleanup pass can be added if the table's size ever matters.
- **`app.state.secret_box`**: built once in `create_app()` from `settings.encryption_key`
  (`None` if unset), not lazily per-request and not checked at lifespan startup like
  `jwt_secret` — agents are the only feature that needs it so far, and failing at first use
  (500, "Encryption key is not configured") keeps every other endpoint working without it.

## Consequences
- The suite JSON Schema (`suite_json_schema()`, for the web YAML editor) reflects these field
  names directly, since it's generated from the same pydantic models, not hand-maintained.
- `TestCase.expectations`/`TestCase.context` are JSONB *objects*, not arrays, per the existing
  column types (`dict[str, Any]`), so the API wraps a case's `expect` list as
  `{"judges": [...]}` and its `context` list as `{"documents": [...]}` when syncing rows.
- When Prompt 12 builds the real attack library, it registers ids via `register_attack` instead
  of this module hardcoding them, and can add `variants`/`mutate` as additional `Case` fields
  without touching the judge or parser modules.

## Amendment (2026-09-26)
- The attack registry is now a constant, `ATTACKS = frozenset({...})`: nothing registered
  ids at runtime, so the mutable set, `register_attack` and `registered_attacks` were an
  unused extension point. Prompt 12 replaces the constant with its generators.
- `obfuscate` and `attack_params` still parse, but a run of a case that sets either is
  refused up front, like `mutations` (ADR 0016 amendment), until the attack library exists.

## Amendment (2026-09-26, C1/C2)
- The real attack library replaced the placeholder constant: see
  [ADR 0021](0021-attack-library-and-mutator.md). `ATTACKS` now re-exports
  `agentprobe_core.attacks.registry.ATTACK_IDS` (15 ids). `obfuscate`/`attack_params`/
  `mutations` are still refused at run time — the library exists, but wiring its output into
  `plan_attempts` is a separate, not-yet-done follow-up (ADR 0021's own "not wired in" section).
- The agent config union is `http` | `python`. The `mcp` config was a placeholder with no
  adapter behind it; the MCP adapter (C3, Prompt 14) defines its own. The `adapter_type`
  CHECK still allows `mcp`.
