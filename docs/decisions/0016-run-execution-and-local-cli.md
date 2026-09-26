# 0016: Run execution and the local CLI run

Status: accepted (2026-09-25). Implements PLAN.md B1.7 and D1.1 (with the local half of D2.1).

## Context
PLAN.md Q6 requires exactly one implementation of how a run executes, shared by the CLI's local run and the server runner (B2.3). SPEC.md §4.3 asks for a full trace per attempt, timeouts, retries and concurrency. SPEC.md §4.10 lists the CLI commands but leaves the exit codes, the default threshold, the run file format and local baselines open.

## Decision

### Core: `agentprobe_core/runner.py`
- **`execute_attempt(case, adapter, judges, llm, limits)`**: one attempt, pure and DB-free. It returns an `AttemptResult` holding the input, the whole `AgentResponse` (steps, tool calls with arguments, usage, latency), every judge verdict, tokens, the agent's estimated cost, and the judges' own LLM cost. It never raises, except on cancellation. Every failure becomes an `AttemptError` with one of these kinds:
  - `timeout`: the agent didn't answer within `agent_timeout_s`, a backstop over the adapter's own timeout;
  - `agent`: the agent answered with a failure;
  - `unreachable`: the adapter's retryable failures ran out;
  - `judge`: a judge returned `error`, raised, or timed out;
  - `budget`: `BudgetExceeded` or `QuotaExhausted`;
  - `internal`: the adapter raised.

  Status is `passed`, `failed` or `error`, the same values as `run_results.status`. A judge `error` makes the attempt an `error`, not a `failed`: the agent wasn't judged wrong, AgentProbe couldn't judge it.
- **`AgentResponse.retryable`** is new. The HTTP adapter sets it when its last failure was one that couldn't have reached the agent (connect failure, 429/502/503/504). The run loop retries only `unreachable` attempts: full-jitter backoff through the existing `with_backoff`, 2 retries by default. Timeouts and agent errors are never retried, for ADR 0012's reason: the agent may already have acted.
- **`finalize_run(results, suite=...)`** groups attempts by case and builds `CaseSummary` (ADR 0014), with the label and Wilson interval. It runs each case's `consistency` judges over the answered attempts' outputs, and computes the suite pass rate with its bootstrap CI (`statistics.bootstrap_resamples`), tokens, and both costs.
  - The consistency verdict is reported per case (`CaseResult.consistency`) and listed among the failures. It does **not** change the attempts' pass counts: the statistics are per attempt, and consistency is per case.
- **`run_suite(suite, adapter, judges, llm, options, on_result=, cancel=)`**:
  - Workers in a `TaskGroup` pull from one queue of (case, attempt index) pairs, so concurrency is bounded by `options.concurrency`.
  - Each final attempt is streamed to the async `on_result`. An exception from `on_result` aborts the run and cancels the other workers; the server will persist through it.
  - Setting `cancel` (an `asyncio.Event`) cancels the in-flight attempts and returns a `cancelled` summary of the attempts that finished. Cancelling the task itself cancels the workers too.
  - A suite that can't run is refused with `ValueError` before any call: a case with `attack` but no `input` (generation lands with the attack library), or one with `mutations` (it needs the mutator). The expansion point is `_plan()`; mutation variants will expand there. **Amended 2026-09-26:** a case that sets `obfuscate` or `attack_params` is refused the same way until the attack library (C1) exists; before, both were silently ignored.
- **Costs.** The agent's cost is estimated only when its config gives a `Price` and the response reports both input and output tokens; otherwise it is `None`, not 0. The judges' spend is metered per attempt by wrapping the shared `LLMClient`, so the run's budget guard still applies; cache hits count as $0. The two costs stay separate (PLAN.md §2 #8).
- `AttemptResult` and `RunSummary` are frozen pydantic models. Their JSON is the local run file and the natural body for the future ingest endpoint (PLAN.md §2 #2).

### CLI (`packages/cli`, Typer + Rich)
- **Exit codes**, documented in `--help`:

  | Code | Meaning |
  |---|---|
  | 0 | passed |
  | 1 | pass rate below `--fail-under` |
  | 2 | regression against the baseline |
  | 3 | usage, config or suite error |
  | 4 | infrastructure error |

  When several apply, precedence is 4 > 2 > 1: an unreachable agent's pass rate means nothing, and a regression is the more specific failure. Code 4 covers any `unreachable`, `budget` or `internal` attempt.
- **`--fail-under` defaults to 1.0**: every case must pass, as in any test runner. A flaky agent needs an explicit tolerance. It is compared against the point estimate (PLAN.md §2 #9).
- Click exits 2 on usage errors, which would read as a regression. A `TyperGroup` subclass sets 3 on every `UsageError` instead.
- **`agentprobe.yaml`** holds `llm.provider`, `run.concurrency`/`run.retries`, and named agents: `http` (the full `HttpAdapterConfig`, plus `secret_headers_env` and `price`) or `python` (`module:callable`, importable from the config's directory).
  - Secret headers come from environment variables and never from the YAML (the adapter already rejects plaintext `Authorization`).
  - `--agent` picks an agent other than the suite's `agent:`.
  - `--mock` forces `LLM_PROVIDER=mock`. Otherwise env `LLM_PROVIDER` beats the YAML. An LLM client is built only when the suite uses `llm_rubric` or `consistency`.
- **Private targets.** The CLI runs on the user's own machine, where a localhost agent is the normal case, so it grants the policy half of ADR 0012's opt-in itself. The agent still needs `allow_private: true`, and metadata and other blocked ranges stay blocked. The server keeps requiring `ALLOW_PRIVATE_TARGETS=1`.
- **Run store.** Runs are saved to `$AGENTPROBE_STATE_DIR/runs/<UTC stamp>-<suite>-<id8>.json` (default `.agentprobe/`). The suite name is reduced to `[A-Za-z0-9_.-]`, so it can never be a path component.
- **Baselines.** `baseline set <run-file> [--name main]` copies the file to `baselines/<name>.json`, names limited to `[A-Za-z0-9_.-]{1,64}`. `--baseline` and `compare` accept a file path or a saved name, matching SPEC's `--baseline main` for when D2.1 adds remote branches. Runs of different suites are refused. Only shared cases are compared (ADR 0014).
- **Untrusted terminal output.** Judge reasons and errors can quote agent output, and a run file can come from anyone. So every string from a run is printed as a Rich `Text` (never markup), with control characters shown as `\xNN`. Rich's `Text` strips only a few control codes and lets ESC through, which a test caught.
- `--json` prints `{file, exit_code, run, regression}` on stdout. Progress goes to stderr.

## Consequences
- B2.3 calls `run_suite` with a DB-writing `on_result` and a `cancel` event driven by the run's status. B2.3 must not add a run loop of its own.
- The CLI stops a run at its first infrastructure error by setting `run_suite`'s `cancel` event from `on_result`. The run is saved as `cancelled`, the report says "Stopped early", and the CLI exits 4. Without that, a down agent would burn every attempt's retries: minutes for the smoke suite instead of about 20 s. This is CLI policy on the shared hook, not run logic; `run_suite` itself keeps going, and the server can choose either behaviour.
- The regex judge still blocks the event loop for up to 0.25 s per timeout (see PROGRESS known issues). No run-level time budget was added yet.
- Files within one second sort by their random id suffix, not by start time. Use `started_at` inside the file for ordering.
