"""HTTP adapter (SPEC.md §4.2, PLAN.md §2 #11-#12, ADR 0012).

One JSON request per attempt, built from `request_template`; the JSON response is mapped
through JSONPath expressions. Every connection, including redirect hops and retries, goes
through the SSRF guard (`ssrf.py`). Request headers are never logged, and secret header
values stay in `SecretStr` until the request is built.
"""

import asyncio
import json
import random
import re
import ssl
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpcore
import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    SecretStr,
    ValidationError,
    field_validator,
)

from agentprobe_core.adapters.ssrf import (
    GuardedBackend,
    Resolver,
    TargetBlocked,
    TargetPolicy,
    system_resolver,
)
from agentprobe_core.adapters.types import (
    AgentResponse,
    ErrorStep,
    MessageStep,
    TokenUsage,
    ToolCallStep,
    TraceStep,
)
from agentprobe_core.llm.limits import Clock, SystemClock, with_backoff

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
PROBE_INPUT = "Hello! This is a connection test from AgentProbe."
_RETRY_STATUS = frozenset({429, 502, 503, 504})
_DEFAULT_PORT = {"http": 80, "https": 443}

# --- headers ------------------------------------------------------------------------------

_FIELD_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")  # RFC 9110 token
_FIELD_VALUE = re.compile(r"[\t\x20-\x7e]*")  # printable ASCII; no CR/LF/NUL
# Set by the HTTP client; a configured value could desync the request's framing.
_CLIENT_HEADERS = frozenset(
    {"host", "content-length", "transfer-encoding", "connection", "keep-alive", "te", "trailer"}
    | {"upgrade", "proxy-connection"}
)
# Credentials belong in the encrypted auth header, never in plaintext config.
_CREDENTIAL_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie"})


def check_header(name: str, value: str, *, secret: bool) -> None:
    """Raises ValueError for a header the adapter won't send. Never echoes the value."""
    if not _FIELD_NAME.fullmatch(name):
        raise ValueError(f"invalid header name {name[:100]!r}")
    lowered = name.lower()
    if lowered in _CLIENT_HEADERS:
        raise ValueError(f"header {name!r} is set by the HTTP client")
    if not secret and lowered in _CREDENTIAL_HEADERS:
        raise ValueError(f"put {name!r} in the encrypted auth header, not in plain headers")
    if not _FIELD_VALUE.fullmatch(value):
        raise ValueError(f"header {name!r} has a control or non-ASCII character in its value")


# --- JSONPath (subset) ----------------------------------------------------------------------

_SEGMENT = re.compile(r"""\.([A-Za-z_][\w-]*)|\[(-?\d+)\]|\['([^']*)'\]|\["([^"]*)"\]""")
_MISSING = object()
Path = tuple[str | int, ...]


def compile_path(path: str) -> Path:
    """Parses the JSONPath subset the response mapping supports: `$`, `.name`, `['name']`,
    `["name"]` and `[n]` (negative counts from the end). No wildcards or filters: a path names
    exactly one value.
    """
    if not path.startswith("$"):
        raise ValueError(f"JSONPath {path!r} must start with $")
    segments: list[str | int] = []
    pos = 1
    while pos < len(path):
        match = _SEGMENT.match(path, pos)
        if match is None:
            raise ValueError(
                f"unsupported JSONPath {path!r} at position {pos}; use $, .name, ['name'] or [n]"
            )
        name, index, single, double = match.groups()
        if index is not None:
            segments.append(int(index))
        else:
            segments.append(name if name is not None else single if single is not None else double)
        pos = match.end()
    return tuple(segments)


def resolve_path(path: Path, document: Any) -> Any:
    """The value at `path`, or `_MISSING`. Iterative, so hostile nesting can't recurse."""
    node = document
    for segment in path:
        if isinstance(segment, int):
            if not isinstance(node, list) or not -len(node) <= segment < len(node):
                return _MISSING
        elif not isinstance(node, dict) or segment not in node:
            return _MISSING
        node = node[segment]
    return node


# --- request template -----------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
DEFAULT_TEMPLATE: dict[str, JsonValue] = {"input": "{{input}}", "context": "{{documents}}"}


def _strings(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    return []


def _joined(documents: Sequence[JsonValue]) -> str:
    return "\n\n".join(d if isinstance(d, str) else json.dumps(d) for d in documents)


def render_template(template: JsonValue, input: str, documents: Sequence[JsonValue]) -> JsonValue:
    """Fills placeholders inside the parsed template, never in JSON text, so an input with
    quotes or braces can't change the request's structure. A string that is exactly one
    placeholder becomes that value (`{{documents}}` a JSON array); inside a longer string the
    documents are joined as text. One pass: a placeholder inside the input stays literal.
    """
    if isinstance(template, str):
        whole = _PLACEHOLDER.fullmatch(template)
        if whole is not None:
            return input if whole[1] == "input" else list(documents)
        return _PLACEHOLDER.sub(
            lambda m: input if m[1] == "input" else _joined(documents), template
        )
    if isinstance(template, list):
        return [render_template(item, input, documents) for item in template]
    if isinstance(template, dict):
        return {key: render_template(item, input, documents) for key, item in template.items()}
    return template


# --- config ---------------------------------------------------------------------------------


class ResponseMapping(BaseModel):
    """JSONPath expressions into the agent's JSON response."""

    model_config = ConfigDict(extra="forbid")

    output: str = "$.output"
    # The list of tool calls; None: the agent doesn't report them. Once set, a response
    # without it is an error, not "no calls", so a wrong path can't pass tool_not_called.
    tool_calls: str | None = None
    tool_name: str = "$.tool"  # within one call
    tool_arguments: str = "$.arguments"  # within one call: an object or a JSON-encoded object
    input_tokens: str | None = None
    output_tokens: str | None = None
    total_tokens: str | None = None  # defaults to input + output when both are mapped

    @field_validator("*")
    @classmethod
    def _valid_path(cls, value: str | None) -> str | None:
        if value is not None:
            compile_path(value)
        return value


class HttpAdapterConfig(BaseModel):
    """An HTTP agent's stored config (`agents.config`). Secrets are not part of it."""

    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    method: Literal["POST", "PUT", "PATCH"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict, max_length=50)
    request_template: JsonValue = Field(default_factory=lambda: dict(DEFAULT_TEMPLATE))
    response: ResponseMapping = Field(default_factory=ResponseMapping)
    timeout_ms: int = Field(default=30_000, gt=0, le=120_000)  # per attempt
    max_retries: int = Field(default=2, ge=0, le=5)
    follow_redirects: bool = False
    # The agent's half of the private-target opt-in; the server's half is TargetPolicy.
    allow_private: bool = False

    @field_validator("url")
    @classmethod
    def _no_credentials(cls, url: HttpUrl) -> HttpUrl:
        if url.username or url.password:
            raise ValueError("credentials in the URL are not allowed; use the auth header")
        return url

    @field_validator("headers")
    @classmethod
    def _plain_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        for name, value in headers.items():
            check_header(name, value, secret=False)
        return headers

    @field_validator("request_template")
    @classmethod
    def _placeholders(cls, template: JsonValue) -> JsonValue:
        names = {m[1] for s in _strings(template) for m in _PLACEHOLDER.finditer(s)}
        if unknown := sorted(names - {"input", "documents"}):
            raise ValueError(
                f"unknown placeholder(s) {unknown}; use {{{{input}}}} and {{{{documents}}}}"
            )
        if "input" not in names:
            raise ValueError("the request template must contain {{input}}")
        return template


# --- adapter --------------------------------------------------------------------------------


class _CallFailed(Exception):
    """An attempt failed; `invoke` turns the last one into an error response."""


class _Transient(_CallFailed):
    """Worth retrying: the request never reached the agent, or the agent asked for a retry."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after(value: str | None) -> float | None:
    """Retry-After in seconds: delta-seconds or an HTTP date (RFC 9110 §10.2.3)."""
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def _tls_failure(exc: BaseException | None) -> bool:
    # __context__ too: httpcore's pool re-raises `from None`, which drops __cause__.
    while exc is not None:
        if isinstance(exc, ssl.SSLError):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _origin(url: httpx.URL) -> tuple[str, str, int]:
    return url.scheme, url.host, url.port or _DEFAULT_PORT.get(url.scheme, 0)


class HttpAdapter:
    """Calls an agent over HTTP. `invoke` never raises for agent-side failures: they come
    back as an `AgentResponse` with `error` set. Use as an async context manager, or call
    `aclose()`.
    """

    def __init__(
        self,
        config: HttpAdapterConfig,
        *,
        secret_headers: Mapping[str, SecretStr] | None = None,
        policy: TargetPolicy | None = None,
        ssl_context: ssl.SSLContext | None = None,
        resolver: Resolver = system_resolver,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
        clock: Clock | None = None,
    ) -> None:
        """`secret_headers` are the decrypted auth header(s); `policy` defaults to the env.
        `resolver` and `network_backend` (the socket layer *under* the SSRF guard) are for
        tests; the guard itself always runs.
        """
        self._config = config
        self._secret_headers = dict(secret_headers or {})
        for name, value in self._secret_headers.items():
            check_header(name, value.get_secret_value(), secret=True)
        self._paths = {
            field: compile_path(path)
            for field, path in config.response.model_dump().items()
            if path is not None
        }
        self._clock = clock or SystemClock()
        self._rng = random.Random()  # noqa: S311 (jitter, not crypto)
        ssl_context = ssl_context or httpx.create_ssl_context()
        transport = httpx.AsyncHTTPTransport(verify=ssl_context, trust_env=False)
        # httpx has no network_backend option, so swap in a pool whose every connection goes
        # through the guard. The tests drive this exact path, so an httpx change fails loudly.
        transport._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            network_backend=GuardedBackend(
                policy=policy or TargetPolicy.from_env(),
                agent_allows_private=config.allow_private,
                resolver=resolver,
                inner=network_backend,
            ),
        )
        # trust_env=False: with HTTP(S)_PROXY set, the proxy would connect to the target
        # itself, past the guard.
        self._client = httpx.AsyncClient(
            transport=transport, trust_env=False, timeout=config.timeout_ms / 1000
        )

    async def __aenter__(self) -> "HttpAdapter":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def invoke(self, input: str, context: Sequence[JsonValue] = ()) -> AgentResponse:
        return await self._call(input, context, max_retries=self._config.max_retries)

    async def test_connection(self) -> AgentResponse:
        """One probe request, no retries. `error` is None when the target passes the SSRF
        policy, the agent answers 2xx JSON and `response.output` maps.
        """
        return await self._call(PROBE_INPUT, (), max_retries=0)

    async def _call(
        self, input: str, context: Sequence[JsonValue], *, max_retries: int
    ) -> AgentResponse:
        body = render_template(self._config.request_template, input, context)
        steps: list[TraceStep] = [MessageStep(role="user", content=input)]
        timeout_s = self._config.timeout_ms / 1000
        latency_ms = 0.0

        async def attempt() -> AgentResponse:
            nonlocal latency_ms
            started, t0 = datetime.now(UTC), time.perf_counter()
            try:
                try:
                    async with asyncio.timeout(timeout_s):  # bounds slow-drip responses too
                        payload = await self._send(body)
                except TimeoutError:
                    raise _CallFailed(f"no response within {timeout_s:g}s") from None
                latency_ms = (time.perf_counter() - t0) * 1000
                return self._map(payload, steps, started, latency_ms)
            except _CallFailed as exc:
                latency_ms = (time.perf_counter() - t0) * 1000
                steps.append(ErrorStep(message=str(exc), timestamp=started, duration_ms=latency_ms))
                raise

        try:
            return await with_backoff(
                attempt,
                max_retries=max_retries,
                clock=self._clock,
                rng=self._rng,
                base_s=0.5,
                cap_s=8.0,
                retry_on=_Transient,
            )
        except _CallFailed as exc:
            return AgentResponse(
                output="",
                steps=steps,
                latency_ms=latency_ms,
                error=str(exc),
                retryable=isinstance(exc, _Transient),
            )

    def _headers(self) -> httpx.Headers:
        headers = httpx.Headers(
            {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "AgentProbe",
            }
        )
        headers.update(self._config.headers)
        for name, value in self._secret_headers.items():
            headers[name] = value.get_secret_value()
        return headers

    async def _send(self, body: JsonValue) -> Any:
        request = self._client.build_request(
            self._config.method, str(self._config.url), json=body, headers=self._headers()
        )
        for _ in range(MAX_REDIRECTS + 1):
            try:
                response = await self._client.send(request, stream=True)
            except TargetBlocked as exc:
                raise _CallFailed(str(exc)) from None
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                if _tls_failure(exc):  # a bad certificate won't fix itself on retry
                    raise _CallFailed(f"TLS failed: {exc}") from None
                raise _Transient(f"could not connect: {exc}") from None
            except httpx.HTTPError as exc:
                # Sent, but no response: not retried, since the agent may have acted on it.
                raise _CallFailed(f"request failed: {type(exc).__name__}: {exc}") from None
            try:
                redirect = response.next_request  # set for a 3xx with a Location header
                if redirect is None:
                    return await self._read_json(response)
                if not self._config.follow_redirects:
                    raise _CallFailed(
                        f"HTTP {response.status_code} redirect, and redirects are off for this "
                        "agent"
                    )
                request = self._next_hop(request, redirect)
            except httpx.HTTPError as exc:
                raise _CallFailed(f"reading the response failed: {type(exc).__name__}") from None
            finally:
                await response.aclose()
        raise _CallFailed(f"more than {MAX_REDIRECTS} redirects")

    def _next_hop(self, previous: httpx.Request, request: httpx.Request) -> httpx.Request:
        """Checks a redirect hop. Its address is checked by the guard when it connects."""
        if request.url.scheme not in _DEFAULT_PORT:
            raise _CallFailed(f"redirect to a {request.url.scheme!r} URL is not allowed")
        if _origin(request.url) != _origin(previous.url):
            for name in self._secret_headers:  # httpx only strips Authorization
                request.headers.pop(name, None)
        return request

    async def _read_json(self, response: httpx.Response) -> Any:
        status = response.status_code
        if status in _RETRY_STATUS:
            retry_after = _retry_after(response.headers.get("retry-after"))
            raise _Transient(f"HTTP {status} from the agent", retry_after=retry_after)
        if not 200 <= status < 300:
            raise _CallFailed(f"HTTP {status} from the agent")
        too_large = _CallFailed(f"the response is larger than {MAX_RESPONSE_BYTES} bytes")
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
            raise too_large
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                raise too_large
        try:
            return json.loads(body)
        except (ValueError, RecursionError):
            raise _CallFailed("the response is not valid JSON") from None

    def _map(
        self, payload: Any, steps: list[TraceStep], started: datetime, latency_ms: float
    ) -> AgentResponse:
        output = resolve_path(self._paths["output"], payload)
        if output is _MISSING or output is None:
            raise _CallFailed(f"response.output ({self._config.response.output}) matched nothing")
        if not isinstance(output, str):
            output = json.dumps(output)
        try:
            return AgentResponse(
                output=output,
                steps=[
                    *steps,
                    *self._tool_calls(payload, started),
                    MessageStep(
                        role="assistant", content=output, timestamp=started, duration_ms=latency_ms
                    ),
                ],
                usage=self._usage(payload),
                latency_ms=latency_ms,
                tool_calls_reported="tool_calls" in self._paths,
            )
        except ValidationError as exc:  # e.g. tool arguments nested past pydantic's limit
            raise _CallFailed(
                f"the response could not be mapped: {exc.error_count()} error(s)"
            ) from None

    def _tool_calls(self, payload: Any, started: datetime) -> list[ToolCallStep]:
        path = self._paths.get("tool_calls")
        if path is None:
            return []
        calls = resolve_path(path, payload)
        if calls is _MISSING:
            raise _CallFailed(
                f"response.tool_calls ({self._config.response.tool_calls}) matched nothing; "
                "set it to null if the agent doesn't report tool calls"
            )
        if calls is None:
            return []
        if not isinstance(calls, list):
            raise _CallFailed("response.tool_calls must point at a list")
        steps = []
        for call in calls:
            name = resolve_path(self._paths["tool_name"], call)
            if not isinstance(name, str):
                raise _CallFailed(
                    f"a tool call has no string at response.tool_name "
                    f"({self._config.response.tool_name})"
                )
            arguments = resolve_path(self._paths["tool_arguments"], call)
            if arguments is _MISSING or arguments is None:
                arguments = {}
            elif isinstance(arguments, str):  # OpenAI-style JSON-encoded arguments
                try:
                    arguments = json.loads(arguments)
                except (ValueError, RecursionError):
                    raise _CallFailed(f"tool call {name[:100]!r}: arguments are not JSON") from None
            if not isinstance(arguments, dict):
                raise _CallFailed(f"tool call {name[:100]!r}: arguments must be an object")
            steps.append(ToolCallStep(tool=name, arguments=arguments, timestamp=started))
        return steps

    def _usage(self, payload: Any) -> TokenUsage:
        def count(field: str) -> int | None:
            path = self._paths.get(field)
            value = resolve_path(path, payload) if path is not None else None
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
            return value if ok else None

        input_tokens, output_tokens = count("input_tokens"), count("output_tokens")
        total = count("total_tokens")
        if total is None and input_tokens is not None and output_tokens is not None:
            total = input_tokens + output_tokens
        return TokenUsage(
            input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total
        )
