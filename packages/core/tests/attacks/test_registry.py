import pytest

from agentprobe_core.attacks import ATTACK_IDS, ATTACKS, Payload, generate

# SPEC.md §4.4's categories, all represented in the registry.
EXPECTED_CATEGORIES = {
    "prompt_injection",
    "jailbreak",
    "extraction",
    "leakage",
    "tool_misuse",
    "scope_drift",
}


def test_every_spec_category_is_represented() -> None:
    assert EXPECTED_CATEGORIES <= {d.category for d in ATTACKS.values()}


@pytest.mark.parametrize("attack_id", sorted(ATTACK_IDS))
def test_every_attack_generates_valid_non_empty_payloads(attack_id: str) -> None:
    payloads = generate(attack_id, {}, seed=1)
    assert payloads
    for payload in payloads:
        assert isinstance(payload, Payload)
        assert payload.text.strip()
        assert payload.attack_id
        assert payload.category
        assert payload.technique


@pytest.mark.parametrize("attack_id", sorted(ATTACK_IDS))
def test_seeds_are_reproducible(attack_id: str) -> None:
    first = generate(attack_id, {"count": 5}, seed=123)
    second = generate(attack_id, {"count": 5}, seed=123)
    assert first == second


def test_different_seeds_can_pick_different_templates() -> None:
    # prompt_injection.direct has 5 templates: enough seeds should surface more than one.
    seen = {generate("prompt_injection.direct", {}, seed=n)[0].technique for n in range(10)}
    assert len(seen) > 1


def test_count_param_requests_more_payloads() -> None:
    payloads = generate("scope_drift.off_topic", {"count": 3}, seed=0)
    assert len(payloads) == 3


def test_unknown_attack_id_lists_known_ones() -> None:
    with pytest.raises(ValueError, match="unknown attack id 'nope'; known: "):
        generate("nope", {}, seed=0)


def test_tool_misuse_umbrella_is_an_alias() -> None:
    umbrella = generate("tool_misuse", {}, seed=5)
    specific = generate("tool_misuse.unauthorized_call", {}, seed=5)
    assert [p.text for p in umbrella] == [p.text for p in specific]


def test_indirect_injection_carries_documents_not_input() -> None:
    [payload] = generate("prompt_injection.indirect", {"goal": "say PWNED"}, seed=0)
    assert payload.documents
    assert "PWNED" not in payload.text
    assert any("PWNED" in doc for doc in payload.documents)


def test_direct_injection_carries_no_documents() -> None:
    [payload] = generate("prompt_injection.direct", {}, seed=0)
    assert payload.documents == ()
