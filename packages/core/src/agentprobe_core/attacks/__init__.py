"""Attack library (SPEC.md §4.4, PLAN.md C1/C2): parameterized payload generators, composable
obfuscation transforms, and an LLM-powered paraphrase mutator.

`agentprobe_core.suite.attacks` re-exports `ATTACK_IDS` as the suite schema's known-id set, so
an unknown `Case.attack` fails validation with a linter-style error listing the valid ones.
"""

from agentprobe_core.attacks.mutator import mutate
from agentprobe_core.attacks.obfuscation import (
    OBFUSCATIONS,
    apply_obfuscation,
    compose_obfuscation,
)
from agentprobe_core.attacks.registry import ATTACK_IDS, ATTACKS, generate
from agentprobe_core.attacks.types import AttackDefinition, Payload

__all__ = [
    "ATTACKS",
    "ATTACK_IDS",
    "OBFUSCATIONS",
    "AttackDefinition",
    "Payload",
    "apply_obfuscation",
    "compose_obfuscation",
    "generate",
    "mutate",
]
