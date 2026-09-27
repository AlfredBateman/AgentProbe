# 0025: CLI remote compare, MCP stdio verification, and packaging

Status: accepted (2026-09-27). Completes PLAN.md D2.1 and SPEC.md §4.10's packaging.

## Context
D2.1 shipped `run --push` (ADR 0020); `compare <a> <b>` and `--baseline <branch>` against
server baselines were left open (PROGRESS.md "Next"). The MCP adapter (ADR 0023) already
allowed stdio transports in `packages/cli/src/agentprobe/config.py` with no code change
needed, but nothing had ever actually launched a real MCP server over stdio end to end — only
permission checks were tested (`packages/core/tests/adapters/test_mcp.py`). Neither the CLI's
own install path (a PyPI wheel, not this repo's uv workspace) nor a README for it existed yet.

## Decision

### `compare`/`--baseline` accept a server run id
`_load_run(ref)` (`packages/cli/src/agentprobe/main.py`) now checks `ref` against
`uuid.UUID(...)` before trying it as a local path or baseline name — a saved baseline's own
name can't collide, since baseline names are chosen by the user and a UUID string is not a
realistic choice. A server run id is fetched with a new `agentprobe.push.fetch(target, run_id,
transport=...)`, which mirrors `push()`'s shape exactly: same `Target`/`PushError`, `GET
/runs/{id}/export?format=json` (already built for the dashboard, ADR 0018), parsed into a
`RunSummary` from its `summary` field. No new server endpoint, no new CLI-side "project id"
concept: `/runs/{id}/export` only needs the run id, and `owned_run`'s ownership check already
works the same way for an API-key principal as for a session (ADR 0018's export was never
API-key-gated before because nothing but a browser called it; the CLI reaches it as a
`CurrentPrincipal`, the same dependency `/ci/report` doesn't use precisely because `/ci/report`
needs `require_api_key`, and export needs neither).

`--push`'s own baseline resolution is unchanged and unrelated: the server already resolves
`baseline_branch` internally and returns `verdict`/`comparison` in the `/ci/report` response
(ADR 0018). This decision is only about `compare`/`run --baseline` being given a raw server run
id directly, for comparing two arbitrary remote runs without going through `--push` at all.

**Exit codes.** `PushError.infra` still decides 4 vs 3, exactly as `--push` already did; `run`
and `compare`'s exception handling both split `PushError` out of the generic
`(ConfigError, ValueError)` catch so `exc.infra` reaches `_fail`. This is not a new exit code
(the CLAUDE.md prompt for this work says exit codes are unchanged) — 4 already meant
"infrastructure error," and an unreachable AgentProbe server fetching a run is exactly that,
the same as an unreachable server during `--push`.

### MCP stdio, actually exercised
`demo-agents/src/agentprobe_demo_agents/mcp_stdio.py` runs the existing
`mcp_server.build_mcp_server()` over `run_stdio_async()` instead of mounting it into the
FastAPI app — same tools, same planted flaws, zero duplicated flaw logic. A new CLI test
(`packages/cli/tests/test_e2e_demo.py`) configures an MCP agent with `transport: stdio`,
`command: sys.executable`, `args: ["-m", "agentprobe_demo_agents.mcp_stdio"]`, and runs a small
two-case suite (not the full `mcp-safety.yaml`, which is 8 cases × 5 runs = 40 subprocess
launches — one per attempt, since stdio has no persistent session to reuse, ADR 0023) so the
offline `pnpm check` suite doesn't pay for 40 process spawns on every run. It proves the same
planted flaw (`issue_refund` ignoring a negative `amount`) fails over stdio exactly as the
existing test proves it over Streamable HTTP.

### Packaging: verified, not asserted
`scripts/verify_wheel.py` builds every workspace wheel (`uv build --all-packages`), creates a
venv this repo's own workspace never touches, installs `agentprobe_core` and `agentprobe` into
it from the built wheels (not an editable install), and checks `agentprobe --help` and a mock
run (a local Python-adapter agent, no network) both work. This is a new CI job (`packaging` in
`.github/workflows/ci.yml`), not a pytest test: it shells out to `uv build`/`uv venv`/`uv pip
install` and spawns the installed console script as a subprocess, which doesn't fit the
integration/redis/live marker scheme (none of those describe "needs its own venv"), and every
other "does the built artifact actually work" check in this codebase (`docker-compose`, F3) is
similarly a separate CI job rather than a pytest-collected test.

`packages/cli/README.md` (new): install, the `agentprobe.yaml` shape, every command, the
`--push` CI recipe (including that the local result is always saved before the upload is
attempted), the exit code table, and the two MCP transports.

## Consequences
- `agentprobe compare`'s server-id path needs `AGENTPROBE_API_URL`/`AGENTPROBE_API_KEY` set,
  identically to `--push`; `_load_run` raises the same `Target.from_env` `PushError` (exit 3)
  when they're missing, so the error message a user sees is already familiar from `--push`.
- `fetch()` and `push()` now share `_error_message(response)` (extracted, no behavior change)
  so their HTTP-error-to-message mapping can't drift.
- The MCP stdio smoke test spawns two real subprocesses per test run (a small, fixed cost);
  the full `mcp-safety.yaml` suite is still only exercised over HTTP in CI, since running it
  over stdio too would be redundant coverage of the same two planted flaws at 20x the process
  spawns.
- `uv build --package X --package Y` isn't valid (only one `--package` flag is accepted per
  invocation in this uv version); `scripts/verify_wheel.py` and the README both use
  `--all-packages` instead, which also builds `agentprobe-api`/`agentprobe-demo-agents` wheels
  that this check doesn't need — harmless, and simpler than fighting the flag.
