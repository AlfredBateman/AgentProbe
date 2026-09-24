import asyncio
import random
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from agentprobe_core.llm import (
    BudgetExceeded,
    Client,
    Completion,
    EmbeddingDimensionMismatch,
    Embeddings,
    LLMClient,
    LLMConfig,
    LLMConfigError,
    MockProvider,
    Price,
    QuotaExhausted,
    create_client,
)
from agentprobe_core.llm.cache import DiskCache
from agentprobe_core.llm.limits import DailyQuota, RateLimiter
from agentprobe_core.llm.types import Message, Role, TransientLLMError, Usage

MSGS: list[Message] = [{"role": "user", "content": "hello"}]


def client(clock: Any, provider: Any | None = None, **config: Any) -> Client:
    return Client(
        LLMConfig(**config), provider or MockProvider(), clock=clock, rng=random.Random(0)
    )


def test_client_satisfies_the_protocol(clock: Any) -> None:
    c: LLMClient = client(clock)  # mypy checks the structural match
    assert c is not None


async def test_default_client_is_the_offline_mock() -> None:
    c = await create_client(LLMConfig.from_env({}))
    assert isinstance(c.provider, MockProvider)
    assert len((await c.embed(["x"])).vectors[0]) == 768


async def test_budget_caps_calls_before_they_are_sent(clock: Any) -> None:
    provider = MockProvider()
    c = client(clock, provider, max_calls_per_run=2)
    await c.complete(MSGS, "agent")
    await c.embed(["x"])
    with pytest.raises(BudgetExceeded, match="2/2 LLM calls"):
        await c.complete(MSGS, "agent")
    assert provider.completion_calls + provider.embedding_calls == 2


async def test_budget_caps_tokens(clock: Any) -> None:
    c = client(clock, max_tokens_per_run=5)
    await c.complete(MSGS, "agent")  # uses more than 5 tokens; it completes, the next can't
    with pytest.raises(BudgetExceeded, match="LLM_BUDGET_MAX_TOKENS_PER_RUN"):
        await c.complete(MSGS, "agent")


async def test_usage_is_priced_and_caps_usd(clock: Any) -> None:
    config = LLMConfig(
        provider="litellm",
        pricing={"mock/agent": Price(input_per_mtok=1_000_000.0, output_per_mtok=0.0)},
        max_usd_per_run=1.0,
    )
    c = Client(config, MockProvider(), clock=clock)
    first = await c.complete(MSGS, "agent")
    assert first.usage.cost_usd == first.usage.prompt_tokens * 1.0
    assert c.budget.usd == first.usage.cost_usd
    with pytest.raises(BudgetExceeded, match="LLM_BUDGET_USD_PER_RUN"):
        await c.complete(MSGS, "agent")


async def test_daily_usd_cap_spans_clients(clock: Any) -> None:
    config = LLMConfig(provider="litellm", pricing={"mock/agent": Price(1_000_000.0, 0.0)})
    quota = DailyQuota(None, clock)
    await Client(replace(config, max_usd_per_day=2.0), MockProvider(), quota=quota).complete(
        MSGS, "agent"
    )
    second_run = Client(replace(config, max_usd_per_day=2.0), MockProvider(), quota=quota)
    with pytest.raises(BudgetExceeded, match="LLM_BUDGET_USD_PER_DAY"):
        await second_run.complete(MSGS, "agent")


async def test_cache_hits_skip_provider_budget_and_limits(clock: Any, tmp_path: Path) -> None:
    provider = MockProvider()
    quota = DailyQuota(None, clock)
    c = Client(
        LLMConfig(max_calls_per_run=1),
        provider,
        clock=clock,
        limiter=RateLimiter(rpm=1, rpd=1, quota=quota, clock=clock),
        cache=DiskCache(tmp_path),
    )
    first = await c.complete(MSGS, "judge", max_tokens=50)
    again = await c.complete(MSGS, "judge", max_tokens=50)
    assert again.cached and not first.cached
    assert (again.text, again.usage) == (first.text, first.usage)
    assert provider.completion_calls == 1
    assert c.budget.calls == 1 and quota.requests("mock/judge") == 1
    # different params are a different key: now the budget (1 call) refuses
    with pytest.raises(BudgetExceeded):
        await c.complete(MSGS, "judge", max_tokens=51)


async def test_cache_survives_a_new_client(clock: Any, tmp_path: Path) -> None:
    await client(clock).complete(MSGS, "agent")  # uncached client doesn't write
    c1 = Client(LLMConfig(), MockProvider(), cache=DiskCache(tmp_path))
    await c1.embed(["a", "b"])
    provider = MockProvider()
    c2 = Client(LLMConfig(), provider, cache=DiskCache(tmp_path))
    hit = await c2.embed(["a", "b"])
    assert hit.cached and provider.embedding_calls == 0 and len(hit.vectors) == 2


def test_corrupt_cache_entry_is_a_miss(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.put("abcd", {"x": 1})
    (tmp_path / "ab" / "abcd.json").write_text("{torn", encoding="utf-8")
    assert cache.get("abcd") is None


class Scripted:
    """A provider that fails with the given errors, then answers."""

    def __init__(self, failures: list[Exception], dims: int = 768) -> None:
        self.failures = failures
        self.calls = 0
        self.dims = dims
        self.in_flight = 0
        self.max_in_flight = 0

    async def complete(self, model: str, messages: Sequence[Message], **_: Any) -> Completion:
        self.calls += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        if self.failures:
            raise self.failures.pop(0)
        return Completion(text="ok", model=model, usage=Usage(3, 2))

    async def embed(self, model: str, texts: Sequence[str], *, dimensions: int) -> Embeddings:
        return Embeddings(vectors=[[0.0] * self.dims for _ in texts], model=model)


async def test_transient_errors_are_retried_and_every_attempt_counts_against_rpd(
    clock: Any,
) -> None:
    provider = Scripted([TransientLLMError("429", status=429, retry_after=None)] * 2)
    quota = DailyQuota(None, clock)
    c = Client(
        LLMConfig(),
        provider,
        clock=clock,
        rng=random.Random(0),
        limiter=RateLimiter(rpm=100, rpd=100, quota=quota, clock=clock),
    )
    result = await c.complete(MSGS, "agent")
    assert result.text == "ok" and provider.calls == 3
    assert len(clock.sleeps) == 2
    assert c.budget.calls == 1  # one logical call against the run budget...
    assert quota.requests("mock/agent") == 3  # ...but three real requests against the day


async def test_quota_exhausted_is_not_retried(clock: Any) -> None:
    provider = Scripted([QuotaExhausted("daily quota")] * 3)
    with pytest.raises(QuotaExhausted):
        await client(clock, provider).complete(MSGS, "agent")
    assert provider.calls == 1


async def test_max_concurrency(clock: Any) -> None:
    provider = Scripted([])
    c = client(clock, provider, max_concurrency=2)
    await asyncio.gather(*(c.complete(MSGS, "agent") for _ in range(8)))
    assert provider.max_in_flight == 2


async def test_embedding_dimension_mismatch_fails_clearly(clock: Any) -> None:
    c = client(clock, Scripted([], dims=3072))
    with pytest.raises(EmbeddingDimensionMismatch, match=r"3072-dimensional.*EMBEDDING_DIM=768"):
        await c.verify_embedding_dim()


async def test_embed_role_is_not_a_completion_role(clock: Any) -> None:
    role: Role = "embedding"
    with pytest.raises(ValueError, match="embed"):
        await client(clock).complete(MSGS, role)


async def test_live_client_refuses_without_run_live() -> None:
    config = LLMConfig(provider="litellm", run_live=False)
    with pytest.raises(LLMConfigError, match="RUN_LIVE=1"):
        await create_client(config)


async def test_live_client_refuses_models_without_a_price() -> None:
    config = LLMConfig(provider="litellm", run_live=True, pricing={})
    with pytest.raises(LLMConfigError, match="no price for"):
        await create_client(config)
