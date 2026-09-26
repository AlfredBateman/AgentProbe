# 0023: MCP adapter

Status: accepted (2026-09-27). Implements PLAN.md C3.

## Context
SPEC.md §4.2 lists an MCP adapter alongside HTTP and Python: connect to an MCP server, list
its tools, and test tool behavior and argument handling. ADR 0010 left `adapter_type=mcp` as a
placeholder with no adapter behind it. The official SDK (`mcp` on PyPI) shipped a v2 rewrite
(2026-07-28 MCP specification) with a materially different API from what most existing
write-ups describe, so the design here follows the current SDK docs
(<https://py.sdk.modelcontextprotocol.io/>) and the SDK's own source, read and smoke-tested
against a real local server before writing the adapter.

## Decision

### SDK version and transports
`mcp==2.2.0`. A case's `call: {tool, arguments}` (already anticipated by ADR 0010) replaces
chat-style `input`; `Case` now accepts `input`, `attack`, or `call` (at least one). The SDK
speaks stdio, Streamable HTTP and SSE; this adapter implements stdio and Streamable HTTP (SSE
is superseded upstream).

### The SSRF guard, ported to httpx2/httpcore2
`mcp` depends on `httpx2` (`pydantic/httpx2`), not `httpx` — a from-scratch rewrite with an
API and internal architecture (transports, connection pools, network backends) that mirrors
httpx/httpcore almost exactly, confirmed by reading both packages' source. `mcp_ssrf.py`
ports `ssrf.py`'s `GuardedBackend` to httpcore2's `AsyncNetworkBackend`, reusing the
address-classification logic (`classify`, `TargetPolicy`, `system_resolver`) as-is;
`resolve_target` gained a `connect_error` parameter (default `httpcore.ConnectError`) so the
one classification function can raise either backend's exception type. `guarded_httpx2_client`
mirrors `HttpAdapter`'s own private-API transport swap (`transport._pool = ...`) since neither
httpx nor httpx2 exposes a public `network_backend` hook.

### One MCP session per call, not one per adapter
The obvious design — connect once in `__aenter__`, reuse the session across a run's attempts —
fails under `run_suite`: attempts run from worker tasks under a `TaskGroup`, and anyio's
cancel scopes are task-affine. A session entered lazily in whichever worker task calls
`invoke()` first, then closed by `aclose()` from the CLI's or the run's own task (a different
one — the CLI's `finally: await adapter.aclose()` runs in the outer task, never a worker),
raises "attempted to exit cancel scope in a different task than it was entered in". This
reproduced with a persistent session, a lock serializing access to it, and a "rebuild the
client after a failure" attempt at recovering — the bug is about which task entered the
scope, not concurrent access. `_call`/`test_connection` now do
`async with self._build_client() as client: ...` per invocation: enter and exit always happen
in the same coroutine (whichever task is running it), so there is no cross-task mismatch to
have. The shared `httpx2.AsyncClient` (HTTP transport only) still lives for the adapter's
lifetime and still pools TCP connections underneath, so the cost is an extra MCP
initialize/list-tools round trip per attempt, not a new socket. Reflected in the module
docstring and a `ponytail:`-style note, since it is a real, deliberate simplification with a
known ceiling: pool sessions instead if MCP servers prove slow enough to handshake that this
matters, most likely by keying a small pool on the calling task.

### Errors: three paths the SDK itself distinguishes, one more from us
Read from `docs/servers/handling-errors.md` and confirmed against a real server:
- **`ToolError`** (raised by a tool): the call **succeeds** with `is_error=True` and the
  message in `content` — the model's turn to see it, so this is a normal `AgentResponse`
  (`error=None`), and the case's judges decide pass/fail. This is deliberate, not an oversight:
  the leaked-customer-list planted flaw (below) *is* a `ToolError`, and it must reach a
  `not_contains` judge, not get swallowed as an adapter failure.
- **`MCPError`** (raised by a tool, or a bad request): a JSON-RPC protocol error, raised to the
  caller. Classified as `_CallFailed` (not retried — the call reached the server and it
  answered, just not with a result).
- **A bare exception** (a crash): the SDK converts it to `is_error=True` with only
  `"Error executing tool <name>"`, no exception detail — already scrubbed before this adapter
  ever sees it, so nothing here needs to re-implement that.
- **A connect failure** (`httpx2`/`httpcore2` `ConnectError`/`ConnectTimeout`/`PoolTimeout`,
  possibly wrapped in an `ExceptionGroup` by anyio's `TaskGroup` during the handshake):
  classified `_Transient`, retried the same way `HttpAdapter` retries a connect failure.
- **Missing or wrong-type arguments never reach a tool at all**: the SDK validates them
  against the tool's own type-hinted schema first and returns the same `is_error=True` shape a
  `ToolError` would. This is why the demo server's planted flaws are about validation the
  *type system can't express* (a business rule like "amount must be positive"), not missing
  argument checks — those are the SDK's job, and a suite testing them is proving the baseline,
  not exercising a flaw.

### Server-side: HTTP only, checked twice
`McpHttpConfig`/`McpStdioConfig` are separate pydantic models (a discriminated union on
`transport`) rather than one model with optional fields, since the two transports don't share
a shape. `apps/api.McpAgentConfig(McpHttpConfig)` — like `HttpAgentConfig(HttpAdapterConfig)`
— inherits the HTTP-only shape directly, so a stored `transport: "stdio"` config is a plain
422 from pydantic, not a runtime check that could be forgotten. `build_adapter("mcp", ...)`
checks `config.get("transport") == "stdio"` before validating and refuses with
`AdapterNotAllowed`, as a second, independent layer (defense in depth, matching the Python
adapter's two-layer refusal). `McpAdapter.__init__` itself refuses stdio when
`agentprobe_api` is already imported (`sys.modules`), the same backstop `adapters/python.py`
uses — belt and suspenders across three call sites, tested independently at each.

### CLI config: nested, not flattened
`apps/agentprobe/config.py`'s `McpAgent` nests `config: McpAdapterConfig` (the core union)
rather than flattening HTTP/stdio fields onto one CLI model: the two transports still don't
share a shape, and nesting reuses the core union with no duplication, at the cost of one extra
level in the YAML (`type: mcp` + `config: {transport: ..., ...}`). `is_registerable()`
(`--push`'s `agent` vs `agent_name` choice, ADR 0020) now also returns true for an MCP agent
over HTTP — the server can have one registered, unlike stdio or the Python adapter.

### The demo MCP server: two flaws the SDK's own validation can't catch
`demo-agents/mcp_server.py`, three tools on the order-management theme the other demo agents
share (`lookup_order`, `search_orders`, `issue_refund`). `build_mcp_server()` is a **factory**,
not a module-level singleton: `MCPServer.session_manager` can only be `run()` once, and
`main.create_app()` is called more than once in this codebase already (once per test module's
own server) — a shared instance broke the second server's lifespan startup the first time this
was tried, caught immediately by the existing test suite. `main.serve_in_background()` was
also changed to build its own app rather than reuse the module-level singleton, for the same
reason (several test modules each call it once).
- **`issue_refund` never validates `amount`**: type-correct (a `float`), so the SDK's schema
  check passes it through, and nothing after that checks it against zero or the order's real
  total. A negative or absurdly large refund still succeeds. This is deliberately *not*
  "missing argument" or "wrong type" — those are the SDK's job (see above) — it's a business
  rule the type system can't express, which is what "argument handling attacks" in the brief
  actually means once the type-level cases are ruled out.
- **`search_orders` leaks its customer list in the `ToolError` message** on a miss, including a
  canary (`AP-CANARY-MCPLEAK...`) entry — the same shape as `search-orders-unknown-email-leaks`
  in `suites/examples/mcp-safety.yaml`.
- `lookup_order` is the well-behaved control: an injection-shaped `order_id` is just a dict
  miss ("not found"), never a crash or a leak.

### Argument-handling attacks are literal suite cases, not new attack-registry entries
C1's attack library (ADR 0021) generates chat-style text payloads; "missing required args,
wrong types, oversized values, injection strings" are argument *shapes*, not text, and
runtime expansion of `attack:`-only cases into anything (chat or MCP) still isn't wired into
`plan_attempts` (ADR 0021's own deferred follow-up). Adding a schema-driven argument-attack
generator now would be scope creep against a feature (live expansion) that doesn't exist yet.
`suites/examples/mcp-safety.yaml` hand-writes all four shapes as literal `call:` cases against
the demo server's own tools, labelled with existing `attack:` ids (`tool_misuse.
argument_tampering`, `leakage.pii`) purely for documentation, the same convention the earlier
example suites already use for literal cases.

### Golden tests
`vulnerabilities.json` gained two entries (`mcp-refund-no-validation`,
`mcp-search-orders-leak`), route `/mcp-tools`, both using `mcp-safety.yaml`. There's no
well-behaved MCP server to serve as a negative control (same situation as the RAG flaw, ADR
0022), so each control is the same tool called correctly, plus (for the leak) `lookup_order`
on an injection-shaped id. `demo_agents.detection.adapter_for` now dispatches on route: the MCP
route builds an `McpAdapter` instead of `HttpAdapter`. 9 of 9 planted flaws are now detected
end to end (mock mode); the mock-mode section of docs/metrics.md is regenerated from the same
run.

## Consequences
- `packages/core` gained three new hard dependencies: `mcp==2.2.0`, `httpx2==2.13.1`,
  `httpcore2==2.13.1` (the latter transitive, pinned by `mcp`/`httpx2`'s own lockstep
  versioning). `demo-agents` depends on `mcp` directly too, for the demo server.
  `pyproject.toml`'s `[tool.ruff.lint.per-file-ignores]` needed no new entries; the MCP code
  doesn't need the `S311`/`RUF001` exemptions C1's attack library did.
- The one-session-per-call design means an MCP suite's attempts each pay a full MCP
  handshake, not just a tool call — slower than HTTP's single request per attempt, and a
  ceiling worth revisiting if a real MCP server under test is slow to handshake.
- `test_connection()` exists for parity with `HttpAdapter` (a future "test connection" UI
  button, E3) but nothing calls it yet, same as `HttpAdapter`'s own today.
- `apps/api`/`packages/cli`'s adapter callers never call `async with adapter:` at all
  (confirmed while debugging the task-affinity bug): `HttpAdapter`'s own `__aenter__`/
  `__aexit__` are already effectively unused in those paths, relying on process/task exit
  instead of an explicit close. `McpAdapter` matches that existing precedent rather than
  introducing a new contract only it follows.
