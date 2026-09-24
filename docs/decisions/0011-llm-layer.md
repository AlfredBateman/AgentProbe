# 0011: LLM layer — providers, free-tier limits, budget, cache

Status: accepted (2026-09-24)

## Context
B1.2 builds `packages/core/llm`. The live backend is Gemini through LiteLLM on the free tier,
where the binding constraint is requests per day, not money. Google doesn't publish free-tier
numbers; they're per project **and per model**, visible only in AI Studio, and the daily count
resets at midnight Pacific. Every CLI invocation is a new process, so an in-memory daily
counter would reset on every run.

## Decision
- **Shape.** `Client` (implements the `LLMClient` protocol) wraps a `Provider` (`MockProvider`
  or `LiteLLMProvider`) in this order: disk cache → per-day USD check → per-run budget →
  concurrency semaphore → [rate limiter → provider] under backoff → pricing and accounting.
  One client per run: its `BudgetGuard` is that run's budget.
- **Roles → models.** Roles are `agent`, `judge`, `attacker`, `summarizer`, `embedding`.
  Defaults live in `config/llm.yaml`, overridden per role by `LLM_MODEL_<ROLE>`; no model
  name is in code. The earlier env names `LLM_MODEL_DEMO_AGENT` / `LLM_MODEL_MUTATOR` become
  `LLM_MODEL_AGENT` / `LLM_MODEL_ATTACKER` to match the roles. Roles are deliberately spread
  over different models (each has its own free-tier quota); the judge, the volume role, gets
  a lite model with a larger daily allowance.
- **Limits.** `LLM_RPM` is a per-model sliding window that waits. `LLM_RPD` is a per-model
  daily counter persisted in `.agentprobe/llm-quota.json` (Pacific-time day) that **fails**
  with `QuotaExhausted` rather than waiting until midnight. Every attempt, including retries,
  counts against RPD; the run budget counts logical calls. A provider 429 whose body names a
  per-day quota is also `QuotaExhausted` and is not retried.
- **Backoff.** Full-jitter exponential (`uniform(0, min(cap, base·2ⁿ))`) on 429/5xx/timeouts,
  waiting at least the provider's Retry-After (header, or Gemini's `retryDelay` in the body).
  A Retry-After over 300 s fails immediately instead of hanging. LiteLLM's own retries are off
  (`num_retries=0`) so there's one retry policy.
- **Budget.** Per run: max calls (reserved before sending, so never overshot), max tokens and
  max estimated USD (known only after a call, so the crossing call completes and the next is
  refused). Per day: estimated USD, persisted with the RPD counters. Estimates use
  `config/pricing.yaml` (paid-tier rates, dated); a live client refuses to start if any
  configured model has no price, so the USD guard is never blind.
- **Safety blocks** are `Completion(blocked=True, block_reason=…)`, never exceptions: Gemini
  returns `finish_reason="content_filter"` with empty content for both prompt and output
  blocks, and other providers raise `ContentPolicyViolationError`; both map to the same result.
- **Cache.** `LLM_CACHE=1` stores responses under `.agentprobe/llm-cache/` keyed by
  SHA-256 of (op, model, messages/texts, params). Hits skip the provider, the limiter, the
  quota and the budget, and come back marked `cached=True`.
- **Mock.** Pure function of the input. The mock judge follows three documented heuristics
  (canary token → fail; refusal phrase → pass; otherwise pass at 0.5) over the text inside
  `<agent_output>` tags; B1.5's judge prompts must use those tags. Its verdicts are **not
  evidence of detection quality**. Fake embeddings are signed feature hashing of character
  trigrams and words, so cosine similarity tracks textual overlap.
- **Embedding dimension.** Requested via `dimensions` (LiteLLM → `outputDimensionality`);
  every embedding result is checked against `EMBEDDING_DIM`, and `create_client` makes one
  embedding call at startup for live clients.
- **Temperature** is optional and omitted by default: Gemini 3+ deprecates it.
- **LiteLLM packaging.** An opt-in extra (`agentprobe-core[live]`, pinned `==1.102.1`,
  hash-locked), imported lazily. Before import we set `LITELLM_LOCAL_MODEL_COST_MAP=True`
  (no remote cost-map fetch) and `CUSTOM_TIKTOKEN_CACHE_DIR=.agentprobe/tiktoken`: LiteLLM
  1.102.1's bundled `cl100k_base` file fails tiktoken's hash check, so tiktoken deletes it and
  downloads the canonical file (hash-verified) once; this keeps that write out of
  site-packages. Unit tests never import LiteLLM: errors are classified by status code and
  class name, and tests inject fake `acompletion`/`aembedding` callables. The 2026 LiteLLM
  CVEs are in the proxy server (admin API, MCP), which we don't use; the March 2026
  compromised releases (1.82.7/1.82.8) are removed from PyPI.
- **Environment check.** The live provider fails with a named error when `SSL_CERT_FILE`,
  `REQUESTS_CA_BUNDLE` or `CURL_CA_BUNDLE` points at a missing file, instead of a deep TLS
  traceback.

## Consequences
- Free-tier survival is enforced locally: a suite that would exceed the day's allowance stops
  with an actionable error naming the variable and the reset time.
- The quota file has no cross-process lock (`ponytail:` in `limits.py`); two concurrent
  processes can undercount by a few requests. The multi-worker server (B2.3) should move the
  counters to Redis or Postgres.
- RPM/RPD are the same for every model. Per-model overrides can be added when a real quota
  table makes the difference matter.
- The canary format (`CANARY-` + 4+ uppercase alphanumerics) is now a contract for B1.3's demo
  agents and B1.8's golden tests.
