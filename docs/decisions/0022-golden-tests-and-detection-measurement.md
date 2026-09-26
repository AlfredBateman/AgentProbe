# 0022: Golden tests and the detection measurement

Status: accepted (2026-09-26). Completes PLAN.md B1.8 and adds `scripts/measure_detection.py`.

## Context
The golden tests are AgentProbe testing itself: every planted flaw in
`demo-agents/vulnerabilities.json` must be detected by a real run, the same cases must pass on
an agent without the flaw, and the regression verdict must tell v1 → v2 from v1 → v1. The same
facts become the published "Detected X of Y" number in docs/metrics.md, in mock mode and, when
the user chooses to spend the quota, in live mode. Several things had no spec: where "detected"
is defined, what counts as a negative control for the RAG bot, and how a live run resumes
across days.

## Decision

### One definition of "detected"
- `agentprobe_demo_agents.detection` holds it, and both the golden tests
  (`demo-agents/tests/test_golden.py`) and the script import it, so the published numbers and
  `pnpm verify` can't disagree. It lives in `demo-agents` because it is about the demo agents
  and already depends on core; it runs suites through core's `run_suite` and the HTTP adapter.
- A flaw is detected when every listed case has at least one attempt a judge **failed**.
  Errors don't count: an agent that crashed or ran out of quota was not caught misbehaving.
- A regression flaw (`baseline_route`) additionally needs a `regression` verdict from
  `compare_runs` naming its case, because that is what AgentProbe reports for a regression; a
  case that merely fails on v2 isn't the product's claim.
- Reasons in the report name the failing judges or error kinds, never the judges' reason text,
  which can quote agent output (untrusted, and it lands in a Markdown file).

### The manifest carries the expectations
Each flaw gained `suite`, `expected` (the label a detection produces), `negative_control`
(`route`, `case_ids`, optional `note`) and, for the regression, `baseline_route`. The support
and vulnerable flaws' controls are the same cases on `/support/v1`. There is no well-behaved RAG
bot, so the RAG control is weaker and says so: the same question without the injected
document, on the same agent.

### Golden tests
- `demo-agents/tests/test_golden.py` (unmarked: offline, deterministic, in `pnpm check` and
  `pnpm verify`): each flaw detected with its expected label; each negative control passes;
  every attack case in the smoke suite is `stable-pass` on `/support/v1`; v1 → v2 is
  `regression` with exactly `refund-outside-window` flagged; and two consecutive v1 runs, which
  draw different seeded flaky outcomes (4/5 then 5/5 on `order-status`), are `no_change`, with
  the first labelled `flaky`.
- `apps/api/tests/test_golden_api.py` (`integration`): one flow through the API and the inline
  backend. The smoke suite against `/vulnerable`, read back from `GET /runs/{id}/results`: the
  manifest's five `/vulnerable` cases are `stable-fail` and nothing else is flagged.
- The existing CLI golden test in `packages/cli/tests/test_e2e_demo.py` stays: it covers the
  CLI path.

### Live mode
- Needs `RUN_LIVE=1`; sets `AGENT_MODE=llm` and `LLM_PROVIDER=litellm` for the process (the
  demo agents are served from a thread of it). Before any call it prints the estimated agent
  and judge calls per model against `LLM_RPD` and today's usage from the quota file, the
  time at `LLM_RPM`, and the per-process call budget, and asks for confirmation.
- **Resume uses a checkpoint of finished attempts, not the LLM response cache.** The brief said
  "resuming across days using the cache", but the cache keys on the prompt: every repeat of a
  case would get attempt 1's answer back, so a 3-run case would look perfectly stable whatever
  the model does. Finished attempts go to `<AGENTPROBE_STATE_DIR>/detection-live.json`, keyed by
  the agent and judge models, suite and route, and are passed to `run_suite(completed=...)` on
  the next start. The first attempt with an error stops the run unsaved (so it's retried on
  resume) and the script says whether the daily quota is the cause.
- One call at a time (`concurrency=1`) with a 120 s adapter timeout, since a call can wait out a
  whole RPM window in the LLM limiter before it's sent.
- `--runs-per-case` defaults to 3, as asked.

## Consequences
- Mock mode measured 7 of 7 detected, 7 of 7 controls passed (docs/metrics.md).
- **Expected live-mode misses, predicted from the code before any live run** (the script
  reports whatever actually happens; nothing was tuned):
  - `support-v2-refund-regression` **cannot be detected at 3 runs per case**, even if the case
    fails every time: 3/3 → 0/3 has a one-sided Fisher p of 1/20 = 0.05, above the 0.025
    per-case budget, and one changed case among nine gives the suite test p = 1/2 (ADR 0014's
    documented 3-run limit). At 5 runs it's 1/252.
  - `vulnerable-unauthorized-delete`: in llm mode the support and vulnerable routes return only
    `output`, never tool calls, so `tool_not_called` passes trivially.
  - `rag-indirect-injection`: in llm mode the RAG route sends only the question to the model; it
    ignores request `context`, so the injected document never reaches it.
  - The other four depend on how the live model treats the vulnerable bot's system prompt
    (which tells it not to share the API key).
- The manifest's suites use rule judges only, so live mode makes no judge calls; its cost is
  agent calls: 87 at 3 runs per case, 145 at 5.
