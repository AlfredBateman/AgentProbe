"""Judges (SPEC.md §4.5): score one attempt's output/trace against a case's `expect:` list.

`evaluate(spec, ctx)` dispatches on `spec.judge` through `REGISTRY`. Rule-based judges and
`llm_rubric` score one attempt; `consistency` scores a case across `ctx.case_outputs`, its
result feeding `run_case_summaries.consistency_score`.
"""

from agentprobe_core.judges.registry import REGISTRY, evaluate
from agentprobe_core.judges.types import JudgeContext, JudgeFn, Judgment, Status

__all__ = [
    "REGISTRY",
    "JudgeContext",
    "JudgeFn",
    "Judgment",
    "Status",
    "evaluate",
]
