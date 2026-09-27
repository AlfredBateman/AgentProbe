# agentprobe

The AgentProbe CLI: run agent test suites locally, gate CI on regressions, and (optionally)
push results to an AgentProbe server.

Every run executes through the same engine the server uses (`agentprobe_core.runner`), so a
local run and a CI run agree — same statistics, same judges, same verdicts.

## Install

```bash
pip install agentprobe
```

or, in a project already using `uv`:

```bash
uv add agentprobe
```

Requires Python 3.12+. `agentprobe --help` should work right after install, with no config.

## Quick start

```bash
agentprobe init                              # scaffolds agentprobe.yaml + suites/example.yaml
agentprobe run suites/example.yaml           # run it, save the result to .agentprobe/runs/
```

`agentprobe.yaml` lists the agents a suite can run against:

```yaml
agents:
  my-agent:
    type: http
    url: http://127.0.0.1:9000/chat
    allow_private: true          # needed for a localhost / private-network agent
    response:
      output: $.output
      tool_calls: $.tool_calls   # omit if the agent doesn't report tool calls
      total_tokens: $.usage.total_tokens
    # secret_headers_env: {Authorization: MY_AGENT_TOKEN}  # value read from the environment

  # my-function:
  #   type: python              # in-process; CLI-only, never runs on the server
  #   target: my_agent:run      # module:callable, returns str or {output, steps}

  # my-mcp-server:
  #   type: mcp
  #   config:
  #     transport: stdio        # or http; stdio is CLI-only (launches a local command)
  #     command: my-mcp-server
  #     args: ["--flag"]
```

`agentprobe run suite.yaml` picks the suite's own `agent:` unless `--agent` overrides it.

## Commands

| Command | What it does |
|---|---|
| `agentprobe init` | Scaffolds `agentprobe.yaml` and an example suite. `--force` overwrites. |
| `agentprobe run SUITE.yaml` | Runs a suite, prints a report, saves the result under `.agentprobe/runs/`. |
| `agentprobe compare A B` | Regression diff between two runs. `A`/`B` are each a run file, a name saved with `baseline set`, or a server run id (a UUID). |
| `agentprobe baseline set RUN.json` | Saves a run as a named baseline (`--name`, default `main`) for `run --baseline NAME`. |

### `run` flags worth knowing

- `--agent NAME` — override the suite's own agent.
- `--fail-under FLOAT` — minimum pass rate (default `1.0`: every case must pass).
- `--baseline REF` — compare against a run file, a saved baseline name, or a server run id; a regression exits `2`.
- `--runs-per-case N`, `--concurrency N` — override the suite's own settings.
- `--mock` — force the mock LLM provider for judges (no live model calls).
- `--json` — print the full result as JSON on stdout, instead of the Rich report.
- `--alpha`, `--min-drop`, `--permutation-draws`, `--bootstrap-resamples` — override the suite's `statistics:` block. See `agentprobe run --help` for the small-N caveat: at 3 runs per case a single broken case can never be flagged, so use 5 or more.
- `--push` — upload the run to a server (below). A regression **on the server** also exits `2`.

## CI usage (`--push`)

```bash
export AGENTPROBE_API_URL=https://your-agentprobe-server.example.com
export AGENTPROBE_API_KEY=ap_...          # a project API key, never committed

agentprobe run suites/regression.yaml \
  --push --branch "$GITHUB_HEAD_REF" --baseline-branch main \
  --git-sha "$GITHUB_SHA" --pr "$PR_NUMBER"
```

- The suite must already exist on the server (uploaded once via the dashboard or API); a
  registered HTTP or MCP-over-HTTP agent is sent by name, a Python or stdio-MCP agent (which
  the server can't run) is sent by name only, as an unregistered agent.
- The local result is always saved to `.agentprobe/runs/` **before** the upload is attempted,
  so a network problem never loses it — rerun `agentprobe run --push` from the same file, or
  push it again later, without repeating the run.
- The server resolves the baseline itself (`--baseline-branch`, default: `--branch`) and
  returns its own verdict; a server-side regression exits `2` even if the run passed locally.
- `AGENTPROBE_API_URL`/`AGENTPROBE_API_KEY` are read from the environment only, never from
  `agentprobe.yaml`, so the key never ends up committed.

## Exit codes

```
0  passed
1  pass rate below --fail-under (default 1.0: every case must pass)
2  regression against the baseline (statistically significant), locally or on the server
3  usage, config or suite error
4  infrastructure error: agent unreachable, LLM budget used up, the server unreachable or
   erroring during --push/a server run id, or an internal error
```

`agentprobe --help` / `agentprobe run --help` print the same table plus the small-N statistics
caveat.

## MCP agents

Both MCP transports work from the CLI: `transport: http` for a server already running
somewhere reachable, and `transport: stdio` (CLI-only — the server refuses it, since it means
launching an arbitrary local command) for one the CLI should start itself. `command`/`args`/
`env` behave like any subprocess launcher; a fresh MCP session is opened per attempt.

## Building from source

```bash
uv build --all-packages -o dist            # builds every workspace package's wheel
pip install dist/agentprobe_core-*.whl dist/agentprobe-*.whl
```

`agentprobe` depends on `agentprobe-core` (the suite schema, adapters, judges, statistics and
LLM layer); both wheels are needed since `agentprobe-core` isn't published on its own index.
