"""HTTP adapter: request template, JSONPath response mapping, retries, limits and secrets.
SSRF behavior lives in test_ssrf.py.
"""

import asyncio
import json
import logging
import ssl
from typing import Any

import httpcore
import pytest
from pydantic import SecretStr, ValidationError

from adapterfakes import FakeBackend, FakeClock, MakeAdapter, http_response
from agentprobe_core.adapters import (
    MAX_RESPONSE_BYTES,
    PROBE_INPUT,
    ErrorStep,
    HttpAdapterConfig,
    MessageStep,
    ToolCallStep,
    build_adapter,
    compile_path,
    render_template,
    resolve_path,
)
from agentprobe_core.adapters.http import _MISSING

SUPPORT_RESPONSE = {  # the demo support/vulnerable bots' flat shape
    "output": "Order 1042 has been deleted.",
    "tool_calls": [{"tool": "delete_order", "arguments": {"order_id": "1042"}}],
    "steps": [{"role": "assistant", "content": "Order 1042 has been deleted."}],
    "usage": {"total_tokens": 5},
}
SUPPORT_MAPPING = {"tool_calls": "$.tool_calls", "total_tokens": "$.usage.total_tokens"}
RAG_RESPONSE = {  # the demo RAG bot's nested shape
    "result": {"text": "Standard shipping takes 3-5 business days.", "citations": ["shipping"]},
    "meta": {"retrieved_doc_ids": ["shipping"], "tokens": {"input": 6, "output": 6}},
}
RAG_MAPPING = {
    "output": "$.result.text",
    "input_tokens": "$.meta.tokens.input",
    "output_tokens": "$.meta.tokens.output",
}


def sent_json(backend: FakeBackend) -> Any:
    return json.loads(backend.sent.split(b"\r\n\r\n", 1)[1])


# --- request template -------------------------------------------------------------------


async def test_default_template_sends_input_and_documents(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response())
    async with make_adapter(backend) as adapter:
        await adapter.invoke("hello", ["doc one", {"title": "t", "text": "doc two"}])
    assert sent_json(backend) == {
        "input": "hello",
        "context": ["doc one", {"title": "t", "text": "doc two"}],
    }
    assert b"content-type: application/json" in backend.sent.lower()


def test_input_cannot_change_the_request_structure() -> None:
    hostile = 'x", "role": "admin", "y": "{{documents}}'
    body = render_template({"q": "{{input}}", "docs": "{{documents}}"}, hostile, ["secret doc"])
    assert body == {"q": hostile, "docs": ["secret doc"]}  # one pass: no re-substitution


def test_placeholders_inside_longer_strings() -> None:
    template = {"messages": [{"role": "user", "content": "Docs:\n{{documents}}\nQ: {{ input }}"}]}
    body = render_template(template, "why?", ["a", {"k": 1}])
    assert body == {"messages": [{"role": "user", "content": 'Docs:\na\n\n{"k": 1}\nQ: why?'}]}


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ({"q": "{{context}}"}, "unknown placeholder"),
        ({"q": "{{documents}}"}, "must contain {{input}}"),
        ("static text", "must contain {{input}}"),
    ],
)
def test_template_is_validated(template: Any, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        HttpAdapterConfig.model_validate(
            {"url": "https://a.example.com", "request_template": template}
        )


async def test_non_object_template(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response())
    async with make_adapter(backend, request_template=["{{input}}", 1, None]) as adapter:
        await adapter.invoke("hi")
    assert sent_json(backend) == ["hi", 1, None]


# --- JSONPath subset ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("$", {"a": [{"b": 1}, {"b": 2}], "c-d": {"x y": 3}}),
        ("$.a[0].b", 1),
        ("$.a[-1].b", 2),
        ("$['c-d']['x y']", 3),
        ('$["c-d"]["x y"]', 3),
        ("$.c-d", {"x y": 3}),
        ("$.a[2]", _MISSING),
        ("$.a.b", _MISSING),
        ("$.missing", _MISSING),
    ],
)
def test_jsonpath(path: str, expected: Any) -> None:
    document = {"a": [{"b": 1}, {"b": 2}], "c-d": {"x y": 3}}
    assert resolve_path(compile_path(path), document) == expected


@pytest.mark.parametrize("path", ["a.b", "$..a", "$.a[*]", "$.*", "$[?(@.a)]", "$.a[", "$ .a"])
def test_unsupported_jsonpath_is_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="JSONPath"):
        compile_path(path)


def test_bad_response_path_is_a_config_error() -> None:
    with pytest.raises(ValidationError):
        HttpAdapterConfig.model_validate(
            {"url": "https://a.example.com", "response": {"output": "result.text"}}
        )


# --- response mapping ---------------------------------------------------------------------


async def test_maps_the_flat_support_shape(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(body=SUPPORT_RESPONSE))
    async with make_adapter(backend, response=SUPPORT_MAPPING) as adapter:
        response = await adapter.invoke("Delete order 1042")
    assert response.error is None
    assert response.output == "Order 1042 has been deleted."
    assert response.tool_calls_reported
    [call] = response.tool_calls
    assert (call.tool, call.arguments) == ("delete_order", {"order_id": "1042"})
    assert response.usage.total_tokens == 5
    assert [type(s) for s in response.steps] == [MessageStep, ToolCallStep, MessageStep]
    user, _, assistant = response.steps
    assert isinstance(user, MessageStep) and user.role == "user"
    assert user.content == "Delete order 1042"
    assert isinstance(assistant, MessageStep) and assistant.role == "assistant"
    assert assistant.duration_ms == response.latency_ms


async def test_maps_the_nested_rag_shape(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(body=RAG_RESPONSE))
    async with make_adapter(backend, response=RAG_MAPPING) as adapter:
        response = await adapter.invoke("How long does shipping take?")
    assert response.error is None
    assert response.output == "Standard shipping takes 3-5 business days."
    assert not response.tool_calls_reported
    assert response.tool_calls == []
    assert response.usage.model_dump() == {
        "input_tokens": 6,
        "output_tokens": 6,
        "total_tokens": 12,
    }


async def test_maps_openai_style_tool_calls(make_adapter: MakeAdapter) -> None:
    body = {
        "choices": [
            {
                "message": {
                    "content": "done",
                    "tool_calls": [
                        {"function": {"name": "lookup", "arguments": '{"id": 7, "deep": [1]}'}}
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }
    mapping = {
        "output": "$.choices[0].message.content",
        "tool_calls": "$.choices[0].message.tool_calls",
        "tool_name": "$.function.name",
        "tool_arguments": "$.function.arguments",
        "total_tokens": "$.usage.total_tokens",
    }
    backend = FakeBackend(http_response(body=body))
    async with make_adapter(backend, response=mapping) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is None
    assert [(c.tool, c.arguments) for c in response.tool_calls] == [
        ("lookup", {"id": 7, "deep": [1]})
    ]
    assert response.usage.total_tokens == 4


async def test_null_tool_calls_means_none_were_made(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(body={"output": "hi", "tool_calls": None}))
    async with make_adapter(backend, response={"tool_calls": "$.tool_calls"}) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is None
    assert response.tool_calls_reported
    assert response.tool_calls == []


@pytest.mark.parametrize(
    ("body", "mapping", "message"),
    [
        ({"answer": "x"}, {}, "response.output ($.output) matched nothing"),
        ({"output": None}, {}, "matched nothing"),
        ({"output": "x"}, {"tool_calls": "$.tool_calls"}, "set it to null"),
        ({"output": "x", "tool_calls": {}}, {"tool_calls": "$.tool_calls"}, "must point at a list"),
        (
            {"output": "x", "tool_calls": [{"arguments": {}}]},
            {"tool_calls": "$.tool_calls"},
            "no string",
        ),
        (
            {"output": "x", "tool_calls": [{"tool": "t", "arguments": "{bad"}]},
            {"tool_calls": "$.tool_calls"},
            "not JSON",
        ),
        (
            {"output": "x", "tool_calls": [{"tool": "t", "arguments": [1]}]},
            {"tool_calls": "$.tool_calls"},
            "must be an object",
        ),
    ],
)
async def test_mapping_failures_are_errors_not_guesses(
    make_adapter: MakeAdapter, body: Any, mapping: dict[str, str], message: str
) -> None:
    backend = FakeBackend(http_response(body=body))
    async with make_adapter(backend, response=mapping, max_retries=3) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert message in response.error
    assert len(backend.connects) == 1  # not retried
    assert isinstance(response.steps[-1], ErrorStep)


async def test_non_string_output_is_kept_as_json_text(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(body={"output": {"answer": 42}}))
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.output == '{"answer": 42}'


async def test_usage_ignores_non_integer_counts(make_adapter: MakeAdapter) -> None:
    body = {"output": "x", "u": {"i": "12", "o": True, "t": -1}}
    mapping = {"input_tokens": "$.u.i", "output_tokens": "$.u.o", "total_tokens": "$.u.t"}
    backend = FakeBackend(http_response(body=body))
    async with make_adapter(backend, response=mapping) as adapter:
        response = await adapter.invoke("hi")
    assert response.usage.model_dump() == {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }


async def test_hostile_nesting_is_an_error_not_a_crash(make_adapter: MakeAdapter) -> None:
    deep = "[" * 100_000 + "]" * 100_000
    backend = FakeBackend(http_response(raw=deep.encode()))
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.error == "the response is not valid JSON"


# --- status codes, retries, limits ----------------------------------------------------------


async def test_retries_503_then_succeeds(make_adapter: MakeAdapter, clock: FakeClock) -> None:
    backend = FakeBackend(
        http_response(503), http_response(429, headers=("Retry-After: 7",)), http_response()
    )
    async with make_adapter(backend, max_retries=2) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is None
    assert len(backend.connects) == 3
    assert clock.sleeps[1] >= 7  # honors Retry-After
    errors = [s for s in response.steps if isinstance(s, ErrorStep)]
    assert [e.message for e in errors] == ["HTTP 503 from the agent", "HTTP 429 from the agent"]


async def test_gives_up_after_max_retries(make_adapter: MakeAdapter, clock: FakeClock) -> None:
    backend = FakeBackend(*[http_response(502)] * 3)
    async with make_adapter(backend, max_retries=2) as adapter:
        response = await adapter.invoke("hi")
    assert response.error == "HTTP 502 from the agent"
    assert response.output == ""
    assert len(backend.connects) == 3
    assert len(clock.sleeps) == 2


async def test_long_retry_after_is_not_waited_out(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(429, headers=("Retry-After: 3600",)), http_response())
    async with make_adapter(backend, max_retries=2) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert len(backend.connects) == 1


@pytest.mark.parametrize("status", [400, 401, 404, 500])
async def test_other_errors_are_not_retried(make_adapter: MakeAdapter, status: int) -> None:
    backend = FakeBackend(http_response(status), http_response())
    async with make_adapter(backend, max_retries=2) as adapter:
        response = await adapter.invoke("hi")
    assert response.error == f"HTTP {status} from the agent"
    assert len(backend.connects) == 1


async def test_connect_errors_are_retried(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(httpcore.ConnectError("connection refused"), http_response())
    async with make_adapter(backend, max_retries=1) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is None
    assert len(backend.connects) == 2


async def test_tls_failures_are_not_retried(make_adapter: MakeAdapter) -> None:
    error = httpcore.ConnectError("certificate verify failed")
    error.__cause__ = error.__context__ = ssl.SSLCertVerificationError("Hostname mismatch")
    backend = FakeBackend(error, http_response())
    async with make_adapter(backend, max_retries=2) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert response.error.startswith("TLS failed")
    assert len(backend.connects) == 1


async def test_timeout_is_an_error(make_adapter: MakeAdapter) -> None:
    class Hangs(FakeBackend):
        async def connect_tcp(self, *args: Any, **kwargs: Any) -> httpcore.AsyncNetworkStream:
            await asyncio.sleep(10)
            raise AssertionError("unreachable")

    async with make_adapter(Hangs(), timeout_ms=50, max_retries=0) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "within 0.05s" in response.error or "could not connect" in response.error


async def test_oversized_response_is_refused(make_adapter: MakeAdapter) -> None:
    big = json.dumps({"output": "x" * MAX_RESPONSE_BYTES}).encode()
    backend = FakeBackend(http_response(raw=big))
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "larger than" in response.error


async def test_oversized_body_without_content_length_is_refused(make_adapter: MakeAdapter) -> None:
    chunk = b"x" * (MAX_RESPONSE_BYTES + 1)
    raw = b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n" + chunk
    backend = FakeBackend(raw)
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.error is not None
    assert "larger than" in response.error


async def test_invalid_json_is_an_error(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(raw=b"<html>oops</html>"))
    async with make_adapter(backend) as adapter:
        response = await adapter.invoke("hi")
    assert response.error == "the response is not valid JSON"


async def test_test_connection_sends_one_probe(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response(503), http_response())
    async with make_adapter(backend, max_retries=3) as adapter:
        response = await adapter.test_connection()
    assert response.error == "HTTP 503 from the agent"  # no retries
    assert sent_json(backend)["input"] == PROBE_INPUT


# --- headers and secrets ----------------------------------------------------------------------


async def test_headers_and_secret_headers_are_sent(make_adapter: MakeAdapter) -> None:
    backend = FakeBackend(http_response())
    secret = {"Authorization": SecretStr("Bearer sk-live-abc")}
    async with make_adapter(
        backend, headers={"X-Tenant": "demo"}, secret_headers=secret, method="PUT"
    ) as adapter:
        await adapter.invoke("hi")
    head = backend.sent.split(b"\r\n\r\n", 1)[0].lower()
    assert head.startswith(b"put /chat ")
    assert b"x-tenant: demo" in head
    assert b"authorization: bearer sk-live-abc" in head


async def test_request_headers_are_never_logged(
    make_adapter: MakeAdapter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    backend = FakeBackend(http_response(503), http_response())
    secret = {"X-Api-Key": SecretStr("sk-never-log-me")}
    async with make_adapter(backend, secret_headers=secret, max_retries=1) as adapter:
        response = await adapter.invoke("hi")
        text = repr(adapter) + repr(adapter.__dict__) + response.model_dump_json()
    assert caplog.records  # httpx/httpcore did log at DEBUG
    assert "sk-never-log-me" not in caplog.text
    assert "sk-never-log-me" not in text


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({"Authorization": "Bearer x"}, "encrypted auth header"),
        ({"Cookie": "a=b"}, "encrypted auth header"),
        ({"Host": "internal"}, "set by the HTTP client"),
        ({"Transfer-Encoding": "chunked"}, "set by the HTTP client"),
        ({"X-A": "ok\r\nX-Injected: 1"}, "control"),
        ({"Bad Name": "x"}, "invalid header name"),
    ],
)
def test_plain_headers_are_validated(headers: dict[str, str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        HttpAdapterConfig.model_validate({"url": "https://a.example.com", "headers": headers})


def test_secret_header_value_is_validated_without_echoing_it() -> None:
    config = HttpAdapterConfig.model_validate({"url": "https://a.example.com"})
    with pytest.raises(ValueError, match="control") as exc:
        build_adapter(
            "http",
            config.model_dump(mode="json"),
            secret_headers={"X-Key": SecretStr("s3cr3t\nX: y")},
        )
    assert "s3cr3t" not in str(exc.value)
