# 0017: Server runner, queue backends and run progress

Status: accepted (2026-09-25). Implements PLAN.md B2.3 and the start/cancel/stream part of B2.4. It supersedes PLAN.md §2 #15 (Arq) and amends [ADR 0008](0008-db-connection-and-test-isolation.md) (see Tests).

## Context
The server must start suite runs, execute them in the background, persist results, traces and judgments, survive crashes, and stream progress. PLAN.md Q6 allows one implementation of how a run executes: core's `agentprobe_core.runner` ([ADR 0016](0016-run-execution-and-local-cli.md)). PLAN.md §2 #15 picked Arq, and QUEUE_BACKEND=inline|arq.

## Decision

### Queue library: Taskiq + taskiq-redis, not Arq
Maintenance status and compatibility, checked on 2026-09-25:
- **Arq 0.28.0:** its README says "In maintenance only mode" (python-arq/arq#510), and it requires `redis<6`. We already pin `redis==8.1.0` (rate limits, pub/sub), so Arq would force a downgrade.
- **SAQ 0.26.4:** actively maintained, but its `redis` extra requires `redis<8`. That is the same conflict.
- **Taskiq 0.12.6 (2026-08) + taskiq-redis 1.2.3:** actively maintained, and taskiq-redis requires `redis>=8,<9`. Its `RedisStreamBroker` uses a Redis stream with a consumer group, so jobs are acknowledged. A job a dead worker took is reclaimed (`XAUTOCLAIM` after `idle_timeout`) and redelivered. `taskiq.api.run_receiver_task` runs a worker inside another process, which is how the tests run the real jobs. `SmartRetryMiddleware` retries a job that raised, with jittered exponential delay.
- **A hand-rolled queue on redis-py streams** would add no dependency, but we would maintain ack, reclaim and job retry ourselves. Rejected.

Everything sits behind `QueueBackend` (`start`, `enqueue`, `cancel`, `recover`, `aclose`), so the library is swappable. `QUEUE_BACKEND=inline|redis`; the old `arq` value is renamed to `redis`.

Two taskiq-redis behaviours to know:
- **`consumer_id`:** the default `$` would skip jobs kicked before the consumer group existed; we set `consumer_id="0"`.
- **Reclaim needs traffic:** the broker only reclaims unacknowledged jobs after it has fetched new messages, so an idle worker never reclaims. The startup sweep below covers this case.

### One run implementation, two ways to schedule it
- **inline** (local development, `pnpm verify`): the API process runs a whole run through core's `run_suite`, at most `INLINE_MAX_RUNS` runs at once (a semaphore) and `RUN_CONCURRENCY` attempts in flight per run.
- **redis** (CI, production): three idempotent jobs, run by `agentprobe_api.worker` (`taskiq worker agentprobe_api.worker:broker`, or `pnpm dev:worker`):
  - `start_run` claims the run and kicks one `run_attempt` per attempt that isn't saved yet;
  - `run_attempt` calls core's `execute_with_retries`;
  - `finalize_run` calls core's `finalize_run` over the saved attempts.

  The worker lives in the package (`apps/api/src/agentprobe_api/worker.py`, because of the src layout), not at `apps/api/worker.py`.
- **Changes to core:** it now exposes `plan_attempts`, `execute_with_retries` and `run_suite(completed=…)`, so neither backend reimplements planning, retry or resume.
  - `run_suite` also no longer interrupts an `on_result` that is saving a finished attempt when the run is cancelled; it waits for it before returning. Found by a test: a cancel landing mid-save tore the save.

### Persistence (`runstore.py`, migration 0003; schema approved by the user)
- **Config snapshot:** at start, `runs.config_snapshot` stores the suite YAML and version, plus the agent's name, adapter type, config and `secret_ref`. It never holds the secret itself. A run executes from its snapshot, so later edits to the suite or agent don't change it. The auth header is decrypted when a job runs.
- **`run_results`:** gains `error_kind`, `score`, `judge_cost_usd`, `retries` (queryable), plus `detail` JSONB: core's `AttemptResult` without `response.steps`, which stay in `traces.steps`. This lets the server rebuild the attempt exactly, to finalize or to resume.
- **`judgments`:** gains `status` (pass/fail/error; `passed` is `status = 'pass'`) and `evidence`.
- **`run_case_summaries`:** gains `errors`.
- **`runs`:** gains `attempts_total`, `attempts_done`, `heartbeat_at`, `ci_lower`, `ci_upper`, and an index on `status`.
- **Idempotency:**
  - an attempt is `INSERT … ON CONFLICT (run_id, case_id, attempt) DO NOTHING`, under a row lock on the run. It is saved only while the run is `running`, so late results of a cancelled or failed run are dropped;
  - `attempts_done` is incremented only when a row was inserted, so exactly one job sees `done == total` and kicks `finalize_run`;
  - summaries are upserts; case-scope consistency judgments are replaced;
  - the run's status moves `running → completed` conditionally.

  A redelivered `run_attempt` checks for its row before calling the agent, so the agent is never called twice for one attempt.

### Lifecycle and policy
- `queued → running → completed | failed | cancelled`.
- `POST /suites/{id}/runs` (202) takes `runs_per_case`, `model` (a label) and `mock` (default true: the mock LLM for judges). It finds the agent by the suite's `agent:` name. It returns 422 if there is no such agent, the agent isn't http, or the suite can't run (`plan_attempts`).
- `POST /runs/{id}/cancel` marks the run cancelled. Inline stops `run_suite` through its cancel event. On Redis, the jobs see the status. Either way the run is summarized over what was saved.
- **Infrastructure errors fail the run** (unreachable agent, LLM budget or quota, internal error): the first attempt with one fails the run with that error and stops the rest, as the CLI does. A summary of the saved attempts is still written.
- **Retries:** an unreachable agent is retried inside core (`RUN_MAX_RETRIES`, full-jitter backoff from `RUN_BACKOFF_BASE_S`). Transient LLM provider errors are retried inside the LLM client (ADR 0011). A job that raises (e.g. a dropped DB connection) is retried by Taskiq.
- **Crash recovery:** `recover()` resumes queued or running runs that a dead process left behind, skipping the attempts they already saved. A run that can't be rebuilt from its snapshot is marked `failed` with the reason.
  - Inline treats every such run as stale at API startup, since only that process ran it. This holds for one API process; use `redis` with several.
  - Redis runs the sweep at worker (and API) startup, for runs whose `heartbeat_at` (or `created_at`) is older than `RUN_STALE_AFTER_S`.

### Progress over SSE
- **`ProgressBus`:** `publish` / `subscribe`, where `subscribe` is a subscription with `next(wait_s)`. It is in-process queues for inline, and Redis pub/sub on `agentprobe:run:{id}` for Redis, where the worker publishes and the API process holding the connection subscribes.
- **Event contents:** events carry ids, statuses and counts only, never agent output.
- **`GET /runs/{id}/stream`:**
  - it subscribes first, then reads the run, so no event falls in between;
  - it sends `snapshot`, then `attempt` / `status` events, with a `: keep-alive` comment every 15 s, and closes on a terminal status;
  - it returns a plain `StreamingResponse` (`text/event-stream`, no-cache, `X-Accel-Buffering: no`). FastAPI 0.141's native SSE (`response_class=EventSourceResponse`) needs a generator endpoint, and we authenticate and subscribe before streaming.
- **The stream-token fallback of ADR 0009 §5:** `POST /runs/{id}/stream-token` needs a user session and run ownership, and returns a 60 s `typ=stream` JWT carrying `run_id`. The stream accepts `?token=` only for that run; access and stream tokens are not interchangeable.

### LLM budget on the Redis backend: deferred (user decision)
Core's budget guard is per LLM client. Each Redis job builds its own client (`verify=False`), so the per-run caps apply per attempt, not per run. The per-host daily USD cap, `LLM_BUDGET_USD_PER_DAY` in `.agentprobe/llm-quota.json`, is the backstop. Mock is the default and live still needs RUN_LIVE=1. Before F4 (deploy), move the run budget and the daily cap to Postgres or Redis, so every worker shares them.

### Tests
- **ADR 0008 amendment:** background work opens sessions through `app.state.sessionmaker`. Tests replace it with `SharedSessions`: every `sessions()` is the test's own savepoint session, under one `asyncio.Lock` that `bind_db` also takes. So workers and requests take turns, and everything still rolls back.
- The Redis tests run the real worker jobs in-process with `run_receiver_task`, against CI's Redis service. They're marked `integration` + `redis` and run in their own verbose CI step.
- **Equivalence:** one test runs the same suite with the same seeds on both backends. It checks that the attempt results (without timings, per case as a multiset) and the persisted summaries are identical.
- fakeredis's TCP server was used to exercise the Redis tests locally, but it doesn't deliver pub/sub messages across connections, so the SSE-over-Redis test is validated in CI only.

## Consequences
- B2.4 adds the results and trace read endpoints on top of these tables; `detail` + `traces.steps` rebuild any attempt.
- Every attempt write takes a row lock on its run, which serializes one run's saves. That is fine at the current scale (≤ 10,000 attempts per run). Batch the saves if it shows.
- On native Windows the worker needs the selector event loop for psycopg, as the API does. Local development uses inline anyway (CLAUDE.md).
