"""The LLM client: cache -> budget -> concurrency -> (rate limit -> provider) with backoff ->
pricing and accounting. One client per run: its BudgetGuard is the run's budget.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, replace
from typing import Any

from agentprobe_core.llm.cache import DiskCache
from agentprobe_core.llm.config import LLMConfig
from agentprobe_core.llm.limits import (
    BudgetGuard,
    Clock,
    DailyQuota,
    RateLimiter,
    SystemClock,
    with_backoff,
)
from agentprobe_core.llm.mock import MockProvider
from agentprobe_core.llm.types import (
    Completion,
    EmbeddingDimensionMismatch,
    Embeddings,
    LLMConfigError,
    Message,
    Provider,
    Role,
    Usage,
)


class Client:
    def __init__(
        self,
        config: LLMConfig,
        provider: Provider,
        *,
        clock: Clock | None = None,
        rng: random.Random | None = None,
        limiter: RateLimiter | None = None,
        quota: DailyQuota | None = None,
        cache: DiskCache | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.budget = BudgetGuard(
            max_calls=config.max_calls_per_run,
            max_tokens=config.max_tokens_per_run,
            max_usd=config.max_usd_per_run,
        )
        self._clock = clock or SystemClock()
        self._rng = rng or random.Random()  # noqa: S311 (jitter, not crypto)
        self._limiter = limiter
        self._quota = quota
        self._cache = cache
        self._concurrency = asyncio.Semaphore(config.max_concurrency)

    async def complete(
        self,
        messages: Sequence[Message],
        role: Role,
        json_schema: dict[str, Any] | None = None,
        *,
        temperature: float | None = None,  # None: the provider default
        max_tokens: int = 1024,
    ) -> Completion:
        if role == "embedding":
            raise ValueError("use embed() for the embedding role")
        model = self.config.models[role]
        key = DiskCache.key(
            op="complete",
            model=model,
            messages=list(messages),
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if self._cache and (hit := self._cache.get(key)) is not None:
            return replace(Completion(**hit), usage=Usage(**hit["usage"]), cached=True)

        result = await self._call(
            model,
            lambda: self.provider.complete(
                model,
                messages,
                role=role,
                json_schema=json_schema,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        )
        result = replace(result, usage=self._account(model, result.usage))
        if self._cache:
            self._cache.put(key, asdict(result))
        return result

    async def embed(self, texts: Sequence[str]) -> Embeddings:
        model = self.config.models["embedding"]
        dim = self.config.embedding_dim
        key = DiskCache.key(op="embed", model=model, texts=list(texts), dimensions=dim)
        if self._cache and (hit := self._cache.get(key)) is not None:
            return replace(Embeddings(**hit), usage=Usage(**hit["usage"]), cached=True)

        result = await self._call(model, lambda: self.provider.embed(model, texts, dimensions=dim))
        result = replace(result, usage=self._account(model, result.usage))
        for vector in result.vectors:
            if len(vector) != dim:
                raise EmbeddingDimensionMismatch(
                    f"{model} returned {len(vector)}-dimensional embeddings but "
                    f"EMBEDDING_DIM={dim}. Pick a model that supports {dim} dimensions "
                    "(LLM_MODEL_EMBEDDING), or change EMBEDDING_DIM (needs a migration)."
                )
        if self._cache:
            self._cache.put(key, asdict(result))
        return result

    async def verify_embedding_dim(self) -> None:
        """One embedding call; raises EmbeddingDimensionMismatch if the model disagrees."""
        await self.embed(["embedding dimension check"])

    async def _call[T](self, model: str, call: Callable[[], Awaitable[T]]) -> T:
        if self._quota is not None:
            self._quota.check_usd(self.config.max_usd_per_day)
        self.budget.reserve_call()

        async def attempt() -> T:
            if self._limiter is not None:
                await self._limiter.acquire(model)
            return await call()

        async with self._concurrency:
            return await with_backoff(
                attempt, max_retries=self.config.max_retries, clock=self._clock, rng=self._rng
            )

    def _account(self, model: str, usage: Usage) -> Usage:
        price = self.config.price(model)
        cost = (
            usage.prompt_tokens * price.input_per_mtok
            + usage.completion_tokens * price.output_per_mtok
        ) / 1_000_000
        priced = replace(usage, cost_usd=cost)
        self.budget.record(priced)
        if self._quota is not None:
            self._quota.add_usd(cost)
        return priced


async def create_client(
    config: LLMConfig | None = None, *, verify: bool = True, clock: Clock | None = None
) -> Client:
    """The client for LLM_PROVIDER. Live clients refuse to start without RUN_LIVE=1 or a
    price for every configured model, and (unless verify=False) check the embedding
    dimension with one call before returning.
    """
    config = config or LLMConfig.from_env()
    clock = clock or SystemClock()
    cache = DiskCache(config.state_dir / "llm-cache") if config.cache else None
    if config.provider == "mock":
        return Client(config, MockProvider(), clock=clock, cache=cache)

    if not config.run_live:
        raise LLMConfigError("LLM_PROVIDER=litellm makes live calls; set RUN_LIVE=1 to allow them")
    for model in set(config.models.values()):
        config.price(model)  # fail at startup, not on the first call
    from agentprobe_core.llm.live import LiteLLMProvider

    quota = DailyQuota(config.state_dir / "llm-quota.json", clock)
    client = Client(
        config,
        LiteLLMProvider(timeout_s=config.timeout_s, state_dir=config.state_dir),
        clock=clock,
        limiter=RateLimiter(rpm=config.rpm, rpd=config.rpd, quota=quota, clock=clock),
        quota=quota,
        cache=cache,
    )
    if verify:
        await client.verify_embedding_dim()
    return client
