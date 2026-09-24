"""LiteLLMProvider with fake LiteLLM callables: response mapping, safety blocks and error
classification, all offline (LiteLLM itself is never imported here).
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentprobe_core.llm.live import LiteLLMProvider, classify
from agentprobe_core.llm.types import (
    JUDGE_VERDICT_SCHEMA,
    LLMError,
    Message,
    QuotaExhausted,
    TransientLLMError,
)

MSGS: list[Message] = [{"role": "user", "content": "hi"}]


def response(content: str | None, finish: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


def provider(result: Any = None, *, raises: Exception | None = None) -> LiteLLMProvider:
    seen: dict[str, Any] = {}

    async def acompletion(**kwargs: Any) -> Any:
        seen.update(kwargs)
        if raises is not None:
            raise raises
        return result

    async def aembedding(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return {"data": [{"embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 4}}

    p = LiteLLMProvider(
        timeout_s=5, state_dir=Path("unused"), acompletion=acompletion, aembedding=aembedding
    )
    p.seen = seen  # type: ignore[attr-defined]
    return p


async def run(p: LiteLLMProvider, json_schema: dict[str, Any] | None = None) -> Any:
    return await p.complete(
        "gemini/x", MSGS, role="judge", json_schema=json_schema, temperature=None, max_tokens=64
    )


async def test_maps_text_usage_and_request_params() -> None:
    p = provider(response('{"pass": true}'))
    result = await run(p, JUDGE_VERDICT_SCHEMA)
    assert result.text == '{"pass": true}' and not result.blocked
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (11, 7)
    seen = p.seen  # type: ignore[attr-defined]
    assert seen["num_retries"] == 0  # retries belong to the client
    assert seen["response_format"]["json_schema"]["schema"] == JUDGE_VERDICT_SCHEMA


async def test_safety_filtered_response_is_a_typed_result() -> None:
    result = await run(provider(response(None, finish="content_filter")))
    assert result.blocked and result.text == ""
    assert "content_filter" in (result.block_reason or "")


async def test_content_policy_exception_is_a_typed_result() -> None:
    class ContentPolicyViolationError(Exception):
        pass

    result = await run(provider(raises=ContentPolicyViolationError("blocked: SAFETY")))
    assert result.blocked and "SAFETY" in (result.block_reason or "")


class RateLimitError(Exception):
    status_code = 429


def test_429_is_transient_with_gemini_retry_delay() -> None:
    err = classify(RateLimitError('... "retryDelay": "12s" ...'))
    assert isinstance(err, TransientLLMError) and err.retry_after == 12.0


def test_429_honors_retry_after_header() -> None:
    exc = RateLimitError("slow down")
    exc.response = SimpleNamespace(headers={"retry-after": "7"})  # type: ignore[attr-defined]
    err = classify(exc)
    assert isinstance(err, TransientLLMError) and err.retry_after == 7.0


def test_daily_quota_429_is_not_retried() -> None:
    err = classify(RateLimitError("quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    assert isinstance(err, QuotaExhausted)


def test_5xx_is_transient_and_4xx_is_permanent() -> None:
    class ServiceUnavailableError(Exception):
        status_code = 503

    class BadRequestError(Exception):
        status_code = 400

    assert isinstance(classify(ServiceUnavailableError("down")), TransientLLMError)
    permanent = classify(BadRequestError("invalid schema"))
    assert type(permanent) is LLMError and "BadRequestError" in str(permanent)


async def test_provider_errors_are_raised_classified() -> None:
    with pytest.raises(TransientLLMError):
        await run(provider(raises=RateLimitError("429")))


async def test_embed_maps_vectors_and_passes_dimensions() -> None:
    p = provider()
    result = await p.embed("gemini/e", ["a"], dimensions=768)
    assert result.vectors == [[0.1, 0.2]] and result.usage.prompt_tokens == 4
    assert p.seen["dimensions"] == 768  # type: ignore[attr-defined]


async def test_temperature_is_omitted_unless_set() -> None:
    p = provider(response("x"))
    await run(p)
    assert "temperature" not in p.seen  # type: ignore[attr-defined]
    await p.complete(
        "gemini/x", MSGS, role="agent", json_schema=None, temperature=0.2, max_tokens=8
    )
    assert p.seen["temperature"] == 0.2  # type: ignore[attr-defined]
