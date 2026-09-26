"""The attack ids a suite may name in `Case.attack` (SPEC.md §4.4). The real generators live
in `agentprobe_core.attacks` (C1); this module only re-exports the id set so the schema's
validator can check against it without a dependency cycle (`suite` -> `attacks` is fine,
`attacks` never imports `suite`).
"""

from agentprobe_core.attacks.registry import ATTACK_IDS as ATTACKS

__all__ = ["ATTACKS"]
