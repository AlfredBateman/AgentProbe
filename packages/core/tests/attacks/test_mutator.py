from agentprobe_core.attacks import generate, mutate
from agentprobe_core.llm.client import Client
from agentprobe_core.llm.config import LLMConfig
from agentprobe_core.llm.mock import MockProvider
from agentprobe_core.llm.types import Completion
from judgefakes import ScriptedLLM


async def test_mock_mode_is_deterministic() -> None:
    client = Client(LLMConfig(), MockProvider())
    first = await mutate("prompt_injection.direct", 3, seed=1, llm=client)
    second = await mutate("prompt_injection.direct", 3, seed=1, llm=client)
    assert [p.text for p in first] == [p.text for p in second]
    assert len(first) == 3


async def test_variants_are_distinct_from_each_other_and_the_base() -> None:
    client = Client(LLMConfig(), MockProvider())
    [base] = generate("jailbreak.roleplay", {}, seed=9)
    variants = await mutate("jailbreak.roleplay", 4, seed=9, llm=client)
    texts = [p.text for p in variants]
    assert len(texts) == len(set(texts)) == 4
    assert base.text not in texts


async def test_blocked_provider_falls_back_to_templates_without_failing() -> None:
    blocked = ScriptedLLM(
        completions=[Completion(text="", model="m", blocked=True) for _ in range(10)]
    )
    variants = await mutate("scope_drift.off_topic", 3, seed=7, llm=blocked)
    assert len(variants) == 3
    assert all(v.text for v in variants)


async def test_a_raising_provider_falls_back_to_templates_without_failing() -> None:
    class Raises:
        async def complete(self, *args: object, **kwargs: object) -> Completion:
            raise RuntimeError("provider unreachable")

        async def embed(self, texts: object) -> object:  # pragma: no cover - unused here
            raise NotImplementedError

    variants = await mutate("scope_drift.off_topic", 2, seed=7, llm=Raises())
    assert len(variants) == 2


async def test_near_duplicate_paraphrases_are_deduped_and_backfilled() -> None:
    same = ScriptedLLM(
        completions=[Completion(text="same paraphrase every time", model="m") for _ in range(10)]
    )
    variants = await mutate("scope_drift.off_topic", 3, seed=7, llm=same)
    assert len(variants) == 3
    assert len({v.text for v in variants}) == 3  # the fallback filled distinct templates


async def test_mutate_never_returns_the_base_payload_itself() -> None:
    [base] = generate("leakage.secrets", {}, seed=2)
    same_text = ScriptedLLM(completions=[Completion(text=base.text, model="m")])
    variants = await mutate("leakage.secrets", 1, seed=2, llm=same_text)
    assert base.text not in [v.text for v in variants]
