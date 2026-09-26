"""Live provider: Gemini (or anything else) through LiteLLM. Imported lazily and only when
LLM_PROVIDER=litellm and RUN_LIVE=1.

Errors are classified by status code and class name rather than isinstance checks, so unit
tests drive this module with fake callables and never import LiteLLM.
"""

import os
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from agentprobe_core.llm.types import (
    Completion,
    Embeddings,
    LLMConfigError,
    LLMError,
    Message,
    QuotaExhausted,
    Role,
    TransientLLMError,
    Usage,
)

_BLOCKED_FINISH = {"content_filter", "safety", "prohibited_content", "blocklist", "spii"}
_TRANSIENT_NAMES = {
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
    "APIConnectionError",
    "Timeout",
}
_RETRY_DELAY = re.compile(r'retryDelay"?\s*:\s*"(\d+(?:\.\d+)?)s"')

Call = Callable[..., Awaitable[Any]]


def _import_litellm(state_dir: Path) -> tuple[Call, Call]:
    # A CA-bundle env var pointing at a missing file breaks every HTTPS call deep inside
    # requests/httpx; say so plainly instead.
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        path = os.environ.get(var)
        if path and not os.path.exists(path):
            raise LLMConfigError(f"{var} points at a missing file ({path}); fix or unset it")
    # No network at import: use the bundled model-cost map, and keep tiktoken's one-time
    # tokenizer download (LiteLLM's bundled copy fails tiktoken's hash check) out of
    # site-packages.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    os.environ.setdefault("CUSTOM_TIKTOKEN_CACHE_DIR", str((state_dir / "tiktoken").resolve()))
    import litellm

    litellm.suppress_debug_info = True
    return litellm.acompletion, litellm.aembedding


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _retry_after(exc: Exception) -> float | None:
    headers = _get(_get(exc, "response"), "headers")
    raw = headers.get("retry-after") if headers is not None else None
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass  # HTTP-date form: fall back to the body
    match = _RETRY_DELAY.search(str(exc))
    return float(match.group(1)) if match else None


def _redacted(text: str) -> str:
    """Provider errors can quote the request (URL, headers). Their text ends up in judge
    reasons, which are stored, exported, shown on public share links and logged, so any
    credential from the environment is cut out first.
    """
    for name, value in os.environ.items():
        if len(value) >= 8 and name.endswith(("_API_KEY", "_TOKEN", "_SECRET")):
            text = text.replace(value, "[REDACTED]")
    return text


def classify(exc: Exception) -> Exception:
    """Maps a provider exception to QuotaExhausted, TransientLLMError or LLMError."""
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    message = _redacted(str(exc))[:500]
    if status == 429 or name == "RateLimitError":
        if "PerDay" in message:  # Gemini's daily quota: retrying today can't succeed
            return QuotaExhausted(f"provider daily quota exhausted: {message}")
        return TransientLLMError(message, status=429, retry_after=_retry_after(exc))
    if name in _TRANSIENT_NAMES or (isinstance(status, int) and status >= 500):
        return TransientLLMError(message, status=status, retry_after=_retry_after(exc))
    return LLMError(f"{name}: {message}")


class LiteLLMProvider:
    def __init__(
        self,
        *,
        timeout_s: float,
        state_dir: Path,
        acompletion: Call | None = None,
        aembedding: Call | None = None,
    ) -> None:
        if acompletion is None or aembedding is None:
            acompletion, aembedding = _import_litellm(state_dir)
        self._acompletion = acompletion
        self._aembedding = aembedding
        self._timeout_s = timeout_s

    async def complete(
        self,
        model: str,
        messages: Sequence[Message],
        *,
        role: Role,
        json_schema: dict[str, Any] | None,
        temperature: float | None,
        max_tokens: int,
    ) -> Completion:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "timeout": self._timeout_s,
            "num_retries": 0,  # the client owns retries (backoff + rate limits)
        }
        if temperature is not None:  # Gemini 3+ deprecates it; omitted unless asked for
            kwargs["temperature"] = temperature
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": json_schema},
            }
        start = time.perf_counter()
        try:
            response = await self._acompletion(**kwargs)
        except Exception as exc:
            if type(exc).__name__ == "ContentPolicyViolationError":
                return Completion(
                    text="",
                    model=model,
                    finish_reason="content_filter",
                    blocked=True,
                    block_reason=_redacted(str(exc))[:500],
                    latency_ms=(time.perf_counter() - start) * 1000,
                )
            raise classify(exc) from exc
        latency_ms = (time.perf_counter() - start) * 1000

        choice = _get(response, "choices")[0]
        finish = _get(choice, "finish_reason")
        text = _get(_get(choice, "message"), "content") or ""
        blocked = str(finish).lower() in _BLOCKED_FINISH
        usage = _get(response, "usage")
        return Completion(
            text=text,
            model=model,
            finish_reason=finish,
            blocked=blocked,
            block_reason=f"provider safety filter (finish_reason={finish})" if blocked else None,
            usage=Usage(
                prompt_tokens=int(_get(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(_get(usage, "completion_tokens", 0) or 0),
            ),
            latency_ms=latency_ms,
        )

    async def embed(self, model: str, texts: Sequence[str], *, dimensions: int) -> Embeddings:
        start = time.perf_counter()
        try:
            response = await self._aembedding(
                model=model, input=list(texts), dimensions=dimensions, timeout=self._timeout_s
            )
        except Exception as exc:
            raise classify(exc) from exc
        usage = _get(response, "usage")
        return Embeddings(
            vectors=[list(_get(item, "embedding")) for item in _get(response, "data")],
            model=model,
            usage=Usage(prompt_tokens=int(_get(usage, "prompt_tokens", 0) or 0)),
            latency_ms=(time.perf_counter() - start) * 1000,
        )
