"""The attack ids a suite may name in `Case.attack` (SPEC.md §4.4).

Until the attack library (C1) exists, `attack` is only a label on a literal case, so this is
just the ids the bundled example suite uses. C1 replaces it with the real generators.
"""

ATTACKS = frozenset({"prompt_injection.direct", "tool_misuse"})
