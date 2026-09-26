"""Shared types for the attack library (SPEC.md §4.4)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Payload:
    """One generated attack payload.

    `text` is what goes in a case's `input`. `documents` is only set for indirect injection:
    the payload lives in a fixture document delivered through the case's `context` /
    `{{documents}}` (PLAN.md §2 #11), not the input itself, so `text` there is an innocuous
    question and `documents` carries the hidden instruction.
    """

    text: str
    attack_id: str
    category: str
    technique: str  # which template/variant produced it, for traceability
    documents: tuple[str, ...] = ()


GenerateFn = Callable[[dict[str, Any], int], list[Payload]]


@dataclass(frozen=True)
class AttackDefinition:
    id: str
    category: str
    description: str
    severity: str  # "low" | "medium" | "high" | "critical"
    generate: GenerateFn
    notes: str  # what a pass/fail looks like, for suite authors
