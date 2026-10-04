# AgentProbe GitHub Action

Runs an [AgentProbe](https://github.com/) suite against an agent, compares it with a baseline,
posts (or updates) a single PR comment with the verdict, and fails the check on a regression or
a pass rate below threshold — using the `agentprobe` CLI's own exit codes ([ADR 0032](../docs/decisions/0032-github-action-and-dogfood-baseline.md)).

## Quick start

Minimal, no server (mock LLM judges, no baseline comparison):

```yaml
- uses: AlfredBateman/AgentProbe/action@v0.1.0
  with:
    suite: suites/regression.yaml
```

With an AgentProbe server, comparing against `main`'s recorded baseline:

```yaml
- uses: AlfredBateman/AgentProbe/action@v0.1.0
  with:
    suite: suites/regression.yaml
    baseline-branch: main
    api-url: ${{ vars.AGENTPROBE_API_URL }}
    api-key: ${{ secrets.AGENTPROBE_API_KEY }}
```

`api-key` is a secret and is empty on a fork PR run (GitHub never exposes repository secrets to
a workflow triggered by a fork). The action detects this and runs in local/mock mode instead of
failing — see [Fork PRs](#fork-prs) below.

## Inputs

| Input | Default | What it does |
|---|---|---|
| `suite` | *(required)* | Path to the suite YAML file. |
| `agent` | *(suite's own `agent:`)* | Override the agent to run against. |
| `config` | `agentprobe.yaml` | Path to the project config file. |
| `fail-under` | `1.0` | Minimum pass rate (point estimate). |
| `mock` | `true` | Force the mock LLM provider for judges (no live model calls). |
| `baseline-branch` | the resolved `branch` | With a server configured: compare against this branch's server-side baseline. |
| `baseline-run` | *(none)* | Path to a local run JSON file to compare against when no server is configured (e.g. a workflow-artifact baseline your own workflow downloaded). Ignored when `api-url`/`api-key` are set. |
| `branch` | PR head ref, or the current ref | This run's branch, sent with `--push`. |
| `git-sha` | `github.sha` | The commit being tested. |
| `pr-number` | from the triggering event | The PR number, if any. |
| `api-url` | *(none)* | AgentProbe server URL. Omit to run without a server. |
| `api-key` | *(none)* | AgentProbe project API key. Pass it as a secret; never commit it. |
| `cli-package` | empty | pip install spec. Empty installs the CLI and its engine from the action's own source, at the ref you pinned. Override with a local wheel path (or a space-separated list of wheel paths) to test an unreleased CLI change. Don't use the bare name `agentprobe`: on PyPI it is an unrelated project. |
| `python-version` | `3.12` | Python version the CLI runs under. |
| `github-token` | `github.token` | Token used to create/update the PR comment. |
| `comment` | `true` | Post or update a PR comment with the result. |

## Outputs

| Output | What it is |
|---|---|
| `pass-rate` | The run's pass rate (point estimate), 0–1. |
| `verdict` | `regression` \| `improvement` \| `no_change` \| `no_baseline`. |
| `run-url` | The dashboard URL for this run, if a server was configured; else empty. |
| `exit-code` | The `agentprobe` CLI's own exit code. See `agentprobe run --help` for the table (0 pass, 1 below threshold, 2 regression, 3 usage error, 4 infrastructure error). |

## What it does

1. Installs the `agentprobe` CLI from the action's own source (`pip install`), unless `cli-package` says otherwise.
2. Runs the suite (`agentprobe run --json`), pushing to a server (`--push`) if `api-url`/
   `api-key` are set, or comparing against `baseline-run` locally otherwise.
3. Formats a PR comment from the result: pass rate with its 95% CI, the verdict against the
   baseline, newly-failing and newly-flaky cases, the top failure clusters (server mode only —
   clustering runs server-side), and a link to the dashboard or the saved local run.
4. Creates or updates one comment per suite and agent on the PR (identified by a hidden marker
   that names the pair, so re-runs edit the same comment and parallel jobs don't overwrite each other).
5. Exits with the CLI's own exit code, so the job — and the PR's required check, once branch
   protection requires it — fails on a regression or a pass rate below `fail-under`.

Every suite/agent/branch name, case id and server-side cluster summary is treated as untrusted
text and escaped for Markdown before it reaches the comment (`action/format_comment.py`); none
of it is ever rendered as HTML or executed.

## Fork PRs

Fork PRs get no repository secrets, so `api-key` is empty on that run — the action detects this
and runs the suite locally in mock mode with no server push, noting so in the job log. Fork PRs
also get a read-only `GITHUB_TOKEN`, which can't create or update PR comments; if posting the
comment fails for this reason, the action logs a warning and continues rather than failing the
job. Neither degradation affects the actual gate: the final step still exits with `agentprobe
run`'s own exit code, so a genuine regression still fails the check even when nobody could
comment on it.

## Development

`format_comment.py` and `post_comment.py` are plain Python (stdlib only, no extra dependency),
run directly by the composite action's steps via `${{ github.action_path }}`. Unit tests for
`format_comment.render_comment` live in `action/tests/`, run by the repo's own `pnpm check`:

```bash
uv run pytest action
```
