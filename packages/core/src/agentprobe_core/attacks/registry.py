"""The attack registry (SPEC.md §4.4, PLAN.md C1): every id a suite's `Case.attack` can name,
resolved to a real generator.
"""

from typing import Any

from agentprobe_core.attacks import (
    direct,
    extraction,
    indirect,
    jailbreak,
    leakage,
    scope_drift,
    tool_misuse,
)
from agentprobe_core.attacks.types import AttackDefinition, Payload

_MODULES = (direct, indirect, jailbreak, extraction, leakage, tool_misuse, scope_drift)

ATTACKS: dict[str, AttackDefinition] = {
    definition.id: definition for module in _MODULES for definition in module.DEFINITIONS
}
ATTACK_IDS: frozenset[str] = frozenset(ATTACKS)


def generate(attack_id: str, params: dict[str, Any] | None = None, seed: int = 0) -> list[Payload]:
    """The payloads `attack_id` generates for `params`, seeded for reproducibility. Raises
    `ValueError` for an unknown id, listing the known ones (the same check the suite schema
    runs at parse time).
    """
    try:
        definition = ATTACKS[attack_id]
    except KeyError:
        raise ValueError(
            f"unknown attack id {attack_id!r}; known: {', '.join(sorted(ATTACK_IDS))}"
        ) from None
    payloads = definition.generate(params or {}, seed)
    if not payloads:
        raise ValueError(f"attack {attack_id!r} generated no payloads")
    return payloads
