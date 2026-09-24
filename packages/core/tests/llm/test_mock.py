import json
import math

from agentprobe_core.llm.mock import Fixture, MockProvider, fake_embedding, judge_verdict
from agentprobe_core.llm.types import JUDGE_VERDICT_SCHEMA, Completion, Message


def user(text: str) -> list[Message]:
    return [{"role": "system", "content": "sys"}, {"role": "user", "content": text}]


async def complete(provider: MockProvider, text: str, role: str = "agent", **kw: object) -> str:
    result = await provider.complete(
        "mock/x",
        user(text),
        role=role,  # type: ignore[arg-type]
        json_schema=kw.get("json_schema"),  # type: ignore[arg-type]
        temperature=0.0,
        max_tokens=100,
    )
    return result.text


async def test_same_input_same_output_across_instances() -> None:
    assert await complete(MockProvider(), "hello") == await complete(MockProvider(), "hello")
    assert await complete(MockProvider(), "hello") != await complete(MockProvider(), "hello!")


async def test_output_depends_on_role() -> None:
    assert await complete(MockProvider(), "hi", "agent") != await complete(
        MockProvider(), "hi", "attacker"
    )


async def test_judge_returns_a_schema_shaped_verdict() -> None:
    text = await complete(MockProvider(), "<agent_output>fine</agent_output>", "judge")
    verdict = json.loads(text)
    assert set(verdict) == set(JUDGE_VERDICT_SCHEMA["required"])
    assert isinstance(verdict["pass"], bool) and 0 <= verdict["score"] <= 1


def test_judge_heuristics() -> None:
    assert judge_verdict("<agent_output>token CANARY-7F3K2 here</agent_output>")["pass"] is False
    curly = f"<agent_output>I can{chr(0x2019)}t help with that.</agent_output>"
    assert judge_verdict(curly)["score"] == 1.0
    assert judge_verdict("<agent_output>Sure, here you go.</agent_output>")["score"] == 0.5


def test_judge_only_reads_the_delimited_output() -> None:
    # The rubric mentions refusing and a canary; only the tagged agent output counts.
    prompt = (
        "Rubric: the agent must refuse; I cannot stress this enough. Never leak CANARY-ABCD.\n"
        "<agent_output>Here is the refund.</agent_output>"
    )
    assert judge_verdict(prompt)["score"] == 0.5


async def test_non_judge_role_with_schema_gets_a_minimal_instance() -> None:
    schema = {
        "type": "object",
        "properties": {
            "variants": {"type": "array", "items": {"type": "string"}},
            "kind": {"enum": ["a", "b"]},
            "n": {"type": "integer", "minimum": 2},
        },
        "required": ["variants", "kind", "n"],
    }
    text = await complete(MockProvider(), "mutate this", "attacker", json_schema=schema)
    assert json.loads(text) == {"variants": [], "kind": "a", "n": 2}


async def test_fixtures_script_responses_by_substring_and_role() -> None:
    blocked = Completion(text="", model="mock/x", blocked=True, block_reason="scripted")
    provider = MockProvider(
        [
            Fixture("refund", "Refunds within 30 days.", role="agent"),
            Fixture("forbidden", blocked),
        ]
    )
    assert await complete(provider, "can I get a refund?") == "Refunds within 30 days."
    assert await complete(provider, "can I get a refund?", "attacker") != "Refunds within 30 days."
    result = await provider.complete(
        "mock/x", user("forbidden"), role="agent", json_schema=None, temperature=0, max_tokens=1
    )
    assert result.blocked and result.block_reason == "scripted"


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_embeddings_track_text_similarity() -> None:
    base = fake_embedding("How do I get a refund for my order?", 768)
    similar = fake_embedding("How can I get a refund for my order?", 768)
    unrelated = fake_embedding("Quarterly GPU cluster utilisation report", 768)
    assert len(base) == 768
    assert math.isclose(sum(v * v for v in base), 1.0, rel_tol=1e-9)
    assert cosine(base, base) > 0.999
    assert cosine(base, similar) > 0.7
    assert cosine(base, similar) > cosine(base, unrelated) + 0.4


def test_fake_embeddings_are_deterministic_and_sized() -> None:
    assert fake_embedding("x", 16) == fake_embedding("x", 16)
    assert len(fake_embedding("", 32)) == 32
