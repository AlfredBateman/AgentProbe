# 0020: Runs of unregistered agents, per-suite-and-agent baselines, and `run --push`

Status: accepted (2026-09-26). Refines PLAN.md §2 #14 and [ADR 0018](0018-results-compare-ci-report-export-share.md).

## Context
PLAN.md §2 #14 allows python-adapter runs "on ingested runs only". But `/ci/report` required a registered agent (ADR 0018), and the server refuses to register python agents (they're CLI-only, ADR 0012), so a CLI python-adapter run could never be ingested. Separately, baselines were keyed on (project, branch): a project with two suites, or two agents, on `main` had one baseline between them, and `/ci/report` could compare a run against another suite's baseline.

## Decision
- **`runs.agent_id` is nullable, with `runs.agent_name` alongside; exactly one is set** (a CHECK, like `judgments`' scope). `agent_name` is a label for an agent the server has no row for. Nothing executable is created from the payload, so ADR 0018's reason for not auto-creating agents still holds.
- **`/ci/report` takes exactly one of `agent` (a registered agent, looked up by name; 422 if missing, as before) or `agent_name`.** An `agent_name` equal to a registered agent's name is a 422: one agent keeps one identity, so its runs never split across two baselines.
- **Baselines are keyed on (project, suite, branch, agent_id or agent_name)**, one unique constraint with `NULLS NOT DISTINCT` (Postgres 15+; Neon and CI run 18). `POST /projects/{id}/baseline` still takes `{branch, run_id}` and copies the suite and agent from the run. `GET /projects/{id}/baselines/{branch}` now needs `suite` (name) and exactly one of `agent` or `agent_name`. `/ci/report` compares against the baseline with its own run's suite and agent. Migration 0004 backfills existing baselines from their run; its downgrade drops what the old schema can't hold.
- **`agentprobe run --push` (the push part of D2.1, built now so the CLI can send `agent_name`)** uploads the finished run to `/ci/report`. The server's URL and project key come from `AGENTPROBE_API_URL` and `AGENTPROBE_API_KEY`, never from `agentprobe.yaml`. It sends a python agent as `agent_name` (it can't be registered) and an http agent as `agent` (the existing contract). `--branch` is required; `--baseline-branch`, `--git-sha`, `--pr` and `--model` are optional. A remote `regression` verdict exits 2 (a local infrastructure error still wins, exit 4). An unreachable server or a 5xx exits 4; a refusal (4xx: bad key, unknown suite) exits 3. The push settings are checked before the suite runs, so a missing key costs nothing.
- `/ci/report` also takes an optional `model` label, stored on the run like `POST /suites/{id}/runs`' (PLAN.md §2 #8).

## Consequences
- An http agent that runs only in the user's CI (e.g. on localhost) must still be registered before its runs can be pushed. If that proves heavy, the CLI could send `agent_name` for http agents the server doesn't know; that needs a lookup and is left for D2.1's remaining work.
- `RunOut.agent_id` can be `null`; the dashboard (E4) shows `agent_name` then.
- Remote `compare <a> <b>` and `--baseline <branch>` against server baselines are still D2.1.
