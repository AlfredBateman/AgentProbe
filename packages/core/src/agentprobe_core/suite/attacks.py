"""Attack registry.

`Case.attack` is validated against this registry so a suite can't reference an attack that
doesn't exist. Prompt 12 (the attack library, SPEC.md §4.4) fills it with real generators via
`register_attack`; until then, the ids used by the bundled example suite are pre-registered
below as placeholders so that suite parses.
"""

_REGISTRY: set[str] = set()


def register_attack(attack_id: str) -> None:
    """Extension point for Prompt 12: register a real attack generator's id."""
    _REGISTRY.add(attack_id)


def is_registered_attack(attack_id: str) -> bool:
    return attack_id in _REGISTRY


def registered_attacks() -> frozenset[str]:
    return frozenset(_REGISTRY)


# Placeholders for suites/examples/support-agent-safety.yaml, until Prompt 12 registers the
# real generators.
register_attack("prompt_injection.direct")
register_attack("tool_misuse")
