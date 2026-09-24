# demo-agents

> **Deliberately vulnerable; fake data only.** `/vulnerable` leaks a fake system prompt and a
> fake API key, calls tools without authorization, and follows injected instructions, on
> purpose. Every "secret" here is a fabricated `AP-CANARY-...` marker. Never point this at
> real data, and never deploy it anywhere but localhost.

One FastAPI process, one port (default `9000`), serving every bundled demo agent under a path
prefix, so AgentProbe (and its own CI) has something to test against.

## Run it

```bash
uv run python -m agentprobe_demo_agents
# or, if the console script is on PATH:
agentprobe-demo-agents
```

Binds to `127.0.0.1:9000` by default. Override the port with `DEMO_AGENTS_PORT`.

## Routes

All chat routes take `POST {prefix}/chat` with `{"input": "...", "context": ["..."]}` and an
optional `X-Admin-Context: true` header, and return JSON.

| Route | Agent | Response shape |
|---|---|---|
| `/support/v1/chat` | Well-behaved support bot. Tools: `lookup_order`, `issue_refund`, `delete_order` (admin-only, correctly enforced). Policy comes from `prompts/support_v1.md`. | `{"output", "tool_calls", "steps", "usage"}` |
| `/support/v2/chat` | Identical code, `prompts/support_v2.md`: a planted regression (refund window widened to 45 days). | same as v1 |
| `/rag/chat` | Document-QA bot over a small keyword-retrieval corpus. Accepts extra `context` documents, which are trusted as retrieved content with no filtering (see `vulnerabilities.json`). | `{"result": {"text", "citations"}, "meta": {...}}` — deliberately different from the others |
| `/vulnerable/chat` | Same tools as support, every safeguard off. See `vulnerabilities.json` for the full list of planted flaws. | same as v1 |

`GET /health` returns `{"status": "ok"}`.

## AGENT_MODE

- `AGENT_MODE=mock` (default): a deterministic rule-based engine imitates an LLM agent,
  including every planted flaw. Fully offline and reproducible — this is what golden tests
  run against.
- `AGENT_MODE=llm`: routes through `agentprobe_core.llm`'s client instead (mock provider by
  default; `RUN_LIVE=1` for a live model). No planted-flaw simulation; useful for manual
  exploration, not for deterministic tests.

## Seeded flakiness

Order lookups on `/support/v1` and `/support/v2` fail intermittently, controlled by
`FLAKY_RATE` (default `0.2`) and `FLAKY_SEED` (default `1337`). `agentprobe_demo_agents.flaky`
exposes `reset(seed)` so tests can pin the exact sequence instead of a real, unreproducible
flake.

## vulnerabilities.json

A manifest of every planted flaw across all four routes: id, route, category, description,
trigger, and the suite case ids that catch it (filled in once suites exist). Golden tests and
the project's README metric ("detected X of Y planted vulnerabilities") both read this file.
