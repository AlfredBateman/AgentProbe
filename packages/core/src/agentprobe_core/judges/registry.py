"""The judge registry: `Case.expect[i].judge` -> the function that evaluates it."""

from agentprobe_core.judges import rules
from agentprobe_core.judges.consistency import consistency
from agentprobe_core.judges.llm_rubric import llm_rubric
from agentprobe_core.judges.types import JudgeContext, JudgeFn, Judgment
from agentprobe_core.suite.judges import JudgeSpec

REGISTRY: dict[str, JudgeFn] = {
    "contains": rules.contains,
    "contains_any": rules.contains_any,
    "not_contains": rules.not_contains,
    "regex": rules.regex,
    "json_schema": rules.json_schema,
    "max_length": rules.max_length,
    "latency_under": rules.latency_under,
    "tool_called": rules.tool_called,
    "tool_not_called": rules.tool_not_called,
    "tool_args_match": rules.tool_args_match,
    "llm_rubric": llm_rubric,
    "consistency": consistency,
}


async def evaluate(spec: JudgeSpec, ctx: JudgeContext) -> Judgment:
    return await REGISTRY[spec.judge](spec, ctx)
