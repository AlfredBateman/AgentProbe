# 0031: Run detail and trace viewer (E4, E5)

Status: accepted (2026-09-28).

## Context
E4 (run detail with live progress) and E5 (trace viewer) need data the API didn't expose: a run's suite name and share state, per-case summaries, a verdict against the baseline, which trace step each judge verdict concerns, and enough on each streamed attempt to show cost and latency live. The pages also had to settle how the browser follows a run's SSE stream, how "virtualize long step lists" fits ADR 0005's plain `<ol>`, and how a shared link opens.

## Decision

### 1. API additions
- `GET /runs/{id}` returns `RunDetailOut`: `RunOut` plus `suite_name` (current), `agent` (as the run's snapshot recorded it), `shared` and `share_expires_at`. The share token itself is still only returned when a link is created.
- `GET /runs/{id}/cases`: the persisted `run_case_summaries` (label, passes, errors, mean score, consistency, mean latency, cost, attack category). It is empty until the run is summarized, and the page aggregates live attempts itself until then. Labels are never computed in the browser: `flaky` is core's call.
- `GET /runs/{id}/verdict`: this run against the baseline of its suite and agent **on its own branch, or `main` for a run without one** (dashboard runs have no branch, and the set-baseline dialog defaults to `main`). The report is core's `compare_runs`, exactly as `GET /runs/compare` serializes it; `is_baseline` when the run is the baseline itself; 404 when no baseline is set there.
- The SSE `attempt` event gains `result_id`, `latency_ms`, `cost_usd` and `score`. `runstore.save_attempt` now returns the new row's id along with the count.
- `GET /results/{id}/trace` gains `run_id` and, per judgment, `step`: the index of the step it concerns, or null for the attempt as a whole.

### 2. Judgment anchors are computed in core
`agentprobe_core.runner.judgment_steps(case, result)` pairs each verdict with its spec (verdicts follow `case.expect` in order, skipping case-level `consistency`) and anchors it:
- tool judges (`tool_called`, `tool_not_called`, `tool_args_match`): the first call to their tool, or null when it was never called;
- `latency_under`: null (it is about the whole attempt);
- every other judge reads the output, so it anchors to the step that carries it: the last assistant message, or the last tool result for an MCP attempt.

No stored data changes. Anchors are derived from the run's own config snapshot at read time.

### 3. Following a live run
`useRunStream` manages the connection only; the page owns the state.
- EventSource's built-in reconnect is not used. Every error closes the source and resyncs through the API client (`GET /runs/{id}` and `/results`), then reconnects with backoff (1, 2, 4, then 8 s). The resync also refreshes an expired session, which EventSource can't.
- Every `snapshot` triggers a resync, because attempts saved before or between connections are not replayed. Resyncs **merge** into the known attempts and never replace them, so an attempt announced during the fetch is never lost.
- A watchdog treats a connection with no snapshot within 10 s (a buffering proxy) or a live stream silent for 45 s as failed. After three failed connections in a row it polls every 3 s until the run ends.
- A refresh mid-run needs nothing special: the first snapshot's resync loads everything saved so far.

The stream is opened on the API directly with a stream token, not through the `/api` rewrite (§7).

### 4. Virtualization is `content-visibility`, not windowing (user decision)
Each step is an `<li>` with `content-visibility: auto` and an intrinsic size, so the browser skips layout and paint for steps off screen. Every step stays in the DOM, which keeps find-in-page, tab order and the list semantics ADR 0005 chose the `<ol>` for; windowing would remove them. Traces longer than 30 steps also open in compact mode.

### 5. Trace presentation
- Steps are native `<details>`. Compact mode closes them all, expanded mode opens them all, and each can still be toggled with the keyboard.
- Untrusted text (inputs, outputs, tool arguments and results, judge reasons) renders only as text children, through `PlainText`, which cuts values at 2,000 characters with a "Show full" control. A test fails the build if any source file uses `dangerouslySetInnerHTML`, `innerHTML` or a markdown renderer.
- Rule and LLM verdicts differ by border (solid vs dashed) **and** a text label ("Rule" / "LLM judge"), never by color alone.
- Comparison aligns steps by index. A step differs when its content differs, ignoring its timestamp and duration; a step with no counterpart differs too. Differing steps are lifted to `surface-2` and carry a "Differs" label: DESIGN.md marks emphasis by surface lift, and the result colors are reserved for pass/fail/flaky.

### 6. The public share page
A copied share link opens `/shared/{token}` (already public in `proxy.ts`), a read-only view of `GET /shared/{token}`: summary, cases and attempts with judge reasons, and no traces or agent config (ADR 0018).

### 7. The /api rewrite buffers SSE, so the browser connects to the API directly
Measured on a real 20-attempt run (`next dev`, Next 16.3.6):
- Straight from the API, events arrived as they happened: the first at 2.7 s, spread over 16.8 s.
- Through the rewrite, all 23 events arrived at once when the run ended (20.4 s), with `Content-Encoding: gzip`.
- Through the rewrite with `Accept-Encoding: identity`, they streamed again (first at 0.6 s). So the cause is Next's response compression, not the proxy itself. Browsers always send `Accept-Encoding: gzip`, and EventSource can't change that.

So, as ADR 0009 §5 planned for this case:
- The page mints a stream token through the rewrite (`POST /runs/{id}/stream-token`) and opens `NEXT_PUBLIC_API_URL/runs/{id}/stream?token=…`, minting a fresh token for every (re)connection since a token lasts 60 s.
- The API adds `Access-Control-Allow-Origin: WEB_ORIGIN` (and `Vary: Origin`) to token-authenticated stream responses only. There are no credentials and no CORS anywhere else.
- `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000` under `next dev`. Where it is unset, the page uses the rewrite, the watchdog finds no snapshot, and it polls.

Turning off `compress` in `next.config` would also have fixed it, but would uncompress every page for one stream, and a CDN in front of production can buffer independently of Next.

## Consequences
- Deploys must set `NEXT_PUBLIC_API_URL` (build time) and `WEB_ORIGIN` (API) for live progress; without them live runs fall back to 3 s polling.
- The run page issues one resync per (re)connection, not per attempt. Judge reasons for an expanded case load on expand and reload as that case's attempts arrive.
- `/verdict`'s `main` default is a convention. A team whose trunk is not `main` sets baselines on their branch and runs with `branch` set, or a future project setting replaces the constant.
- Anchoring depends on `execute_attempt` judging `expect` in order. `judgment_steps` sits next to it in `runner.py`, and a test runs a real attempt through both.
