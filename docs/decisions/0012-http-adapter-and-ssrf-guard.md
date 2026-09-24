# 0012: Adapters, the trace model, and the SSRF guard

Status: accepted (2026-09-24)

## Context
B1.4 builds `packages/core/adapters`: the `AgentAdapter` protocol, the trace step model that
the runner, judges, storage and UI share, the HTTP adapter with an SSRF guard, and the CLI-only
Python adapter. PLAN.md §2 #11–#12 sketched `{{input}}`/`{{context}}` templates and dotted
response paths. The B1.4 brief asks for `{{documents}}` and JSONPath instead. Several details
had no spec: error semantics, retry classes, the config shape, and how the private-target
allowlist combines with the two opt-in flags.

## Decision

### Protocol and trace
- `AgentAdapter.invoke(input, context) -> AgentResponse`, where `context` is the case's
  documents (JSON values). An agent-side failure that survives retries comes back as
  `AgentResponse(error=..., output="")` with an `ErrorStep`; adapters never raise for it. The
  executor records it as an errored attempt (PLAN.md §2 #9).
- Trace steps are a union discriminated on `type`:
  - `message` (role, content);
  - `tool_call` (tool, arguments);
  - `tool_result` (tool, result);
  - `error` (message).

  Each step has a timezone-aware `timestamp` and a `duration_ms`. `duration_ms=None` means
  unknown: a black-box HTTP agent can't time its own tool calls.
- Every trace starts with the user's message. On success it ends with the assistant's message,
  whose duration is the attempt's latency. Failed attempts that were retried stay in the trace
  as error steps. `latency_ms` is the final attempt's duration; it excludes backoff sleeps.
- `tool_calls_reported` is False when the agent doesn't report tool calls. Without it, a
  missing report looks like "no calls made" and passes `tool_not_called`, so B1.5's tool judges
  must refuse to pass when it's False.

### Request template
- The template is JSON. Placeholders are substituted in the parsed structure, never in the JSON
  text, and in one pass. An input containing quotes, braces or `{{documents}}` therefore can't
  change the request's shape.
- Placeholders are `{{input}}` and `{{documents}}`; `{{documents}}` replaces PLAN.md's
  `{{context}}`. A string that is exactly one placeholder becomes the value itself, so documents
  become a JSON array. A placeholder inside a longer string is filled with text: the documents
  are joined by blank lines, with objects serialized as JSON.
- The template must contain `{{input}}`, and unknown placeholders are config errors. The
  default is `{"input": "{{input}}", "context": "{{documents}}"}`, the demo agents' request.
- `Case.context` widens from `list[dict]` to `list[str | dict]`, since documents are often
  plain text (the demo RAG bot takes strings).

### Response mapping
- A JSONPath subset: `$`, `.name`, `['name']`, `["name"]` and `[n]`. It's written in-house
  (about 30 lines) rather than taken from a library. Every mapping names exactly one value, and
  a subset has no filter or eval surface. Wildcards, recursive descent and filters are rejected
  when the config is validated.
- `output` is required. Missing or null is an error; a value that isn't a string is kept as
  JSON text.
- `tool_calls` is optional:
  - `null` in the config means the agent doesn't report tool calls;
  - configured but missing in the response is an error, never "no calls", so a wrong path
    can't silently pass tool judges;
  - a `null` value in the response means no calls.

  `tool_name` and `tool_arguments` are paths within one call. OpenAI-style JSON-encoded
  arguments are parsed.
- Token usage is lenient. A count that is missing or isn't an integer becomes None, and
  `total_tokens` defaults to input + output.
- Config shape: a nested `response` object replaces `response_output_path` and
  `response_tool_calls_path`. `method` is POST, PUT or PATCH; GET is dropped because the
  request needs a body.
- `HttpAdapterConfig` lives in `packages/core`, and the API's `HttpAgentConfig` subclasses it,
  so what's stored is exactly what the adapter runs. This supersedes ADR 0010's "agent config
  validation stays in `apps/api`" for HTTP agents.

### Timeouts and retries
- `timeout_ms` applies per attempt (default 30 s, at most 120 s). httpx enforces it per phase,
  and an overall `asyncio.timeout` also stops slow-drip responses.
- `max_retries` defaults to 2 (at most 5). Retries go through the shared `with_backoff`, which
  gained a `retry_on` parameter: full jitter from 0.5 s, capped at 8 s, and never shorter than
  `Retry-After` (seconds or an HTTP date). A `Retry-After` over 300 s fails instead of waiting.
- Retried: connect errors, connect and pool timeouts, and 429/502/503/504.
- Not retried:
  - anything after the request may have reached the agent (read timeouts, disconnects), since
    the agent may already have acted, e.g. deleted an order;
  - other status codes;
  - TLS failures;
  - SSRF blocks;
  - mapping errors.
- The response body is capped at 2 MiB, checked against `Content-Length` and while streaming.
  Requests send `Accept-Encoding: identity`.
- `test_connection()` sends one probe with no retries. `error is None` means the target passed
  the SSRF policy, the agent answered 2xx JSON, and `response.output` mapped.
- The `.env.example` placeholders `AGENT_TIMEOUT_SECONDS` and `AGENT_MAX_RETRIES` (never read)
  are removed; these are per-agent config.

### Headers and secrets
- Plain header names must be RFC 9110 tokens, and values printable ASCII (so no CR/LF
  injection). Framing headers (`Host`, `Content-Length`, `Transfer-Encoding`, …) are refused.
- `Authorization`, `Proxy-Authorization` and `Cookie` are refused in plaintext config and go in
  the encrypted auth header (ADR 0003) instead.
- Secret header values stay `SecretStr` until the request is built, and validation errors never
  echo them.
- Secret headers are dropped on any cross-origin redirect; httpx strips only `Authorization`.
- Request headers are never logged. A test captures httpx and httpcore at DEBUG and checks that
  no secret value appears.

### SSRF guard
- **Where.** The guard is an httpcore network backend under httpx's connection pool. httpx has
  no option for this, so the adapter swaps `transport._pool`; tests drive that path, so a
  change in httpx fails loudly. Every new connection, including each redirect hop and retry,
  resolves the host once, validates every resolved address, and connects to one of those same
  addresses. With no second lookup there is no DNS-rebinding window.
- **TLS.** TLS still receives the URL's hostname for SNI and certificate verification. A real
  handshake against a local TLS server proves this, and proves that a certificate for another
  name is rejected.
- **Address classes.** Explicit tables, with `ipaddress.is_global` as the fallback, since
  `is_global` alone passes multicast, site-local, IPv4-compatible, NAT64-wrapped loopback and
  Azure's WireServer.
  - *Always blocked:*
    - cloud metadata: 169.254.169.254, 169.254.170.2/.23, 100.100.100.200, 168.63.129.16,
      fd00:ec2::/32;
    - link-local, unspecified and 0/8;
    - multicast, reserved and broadcast;
    - documentation, benchmarking and IETF ranges;
    - IPv4-mapped and IPv4-compatible IPv6, 6to4, Teredo, local-use NAT64 and site-local.
  - *Private*, allowed only with the opt-in: loopback, RFC 1918, CGNAT and IPv6 unique-local.
    Metadata addresses inside CGNAT and unique-local are checked first, so the opt-in never
    opens them.
  - *Well-known NAT64* (64:ff9b::/96) is classified by the IPv4 address it wraps, so NAT64
    deployments still reach public hosts.
  - If any resolved address is blocked, the whole host is blocked.
- **Private opt-in.** A private address is allowed only when all three hold:
  - the agent's config sets `allow_private`;
  - the server sets `ALLOW_PRIVATE_TARGETS=1`;
  - `PRIVATE_TARGET_ALLOWLIST` is empty or lists the host.

  The allowlist narrows private targets for production. It doesn't restrict public targets;
  this is the strictest reading of the brief. `ALLOW_PRIVATE_AGENT_URLS` is renamed to
  `ALLOW_PRIVATE_TARGETS`.
- **Proxies.** `trust_env=False`: with `HTTP(S)_PROXY` set, the proxy would connect to the
  target itself, past the guard.
- **Redirects.** Off by default. When enabled: at most 5 hops, http/https only, and each new
  hop connects through the same guard.
- **Error messages.** The error a user sees never includes a resolved address, so it can't be
  used to map internal DNS. The server log records it.

### Python adapter (CLI only)
- Takes `module:callable` (the attribute may be a dotted path). The callable may be sync (run
  in a thread) or async, takes `(input)` or `(input, context)`, and returns a string or
  `{output, steps}`. An exception or timeout becomes an error response.
- The server can't load it:
  - `agentprobe_core.adapters` doesn't import it;
  - `build_adapter` (the server's constructor for stored agents) refuses `python`;
  - the API rejects python configs (existing);
  - `load_callable` itself refuses in any process that has imported `agentprobe_api`.

  Tests check this with a subprocess that imports the server, and with a scan of the server's
  source for references.

## Consequences
- B1.7's executor consumes `AgentResponse` and treats `error` as an errored attempt. Storage
  persists `steps` as `traces.steps` through `TypeAdapter(list[TraceStep])`.
- B1.5's `tool_called`/`tool_not_called`/`tool_args_match` judges must check
  `tool_calls_reported`.
- E5's trace viewer renders the four step types, with all content as text.
- Known limits:
  - A sync Python callable that hangs keeps its worker thread after the timeout (`ponytail:`
    comment).
  - An OpenAI-style agent that omits `tool_calls` when empty errors under the strict rule. Add
    an explicit "optional" flag if that shape is needed.
  - A hostile server that ignores `identity` can still send gzip. Decoded bytes are counted, so
    one read chunk can expand before the cap applies (bounded by the deflate ratio).
- The adapter relies on httpx's private `_pool` attribute, with httpx pinned at 0.28.1.
