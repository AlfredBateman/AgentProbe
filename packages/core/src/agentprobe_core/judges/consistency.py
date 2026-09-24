"""The `consistency` judge (SPEC.md §4.5): compares a case's answers across repeated
attempts and flags unstable behavior. Unlike the other judges it scores the *case*, not one
attempt -- `ctx.case_outputs` must hold every attempt's output for this case, supplied by
whatever ran the repeated attempts. Its score is what `run_case_summaries.consistency_score`
stores (ADR 0007).

The stability score is the mean pairwise similarity across every pair of outputs: normalized
text similarity always, averaged with embedding cosine similarity when `ctx.llm` is given
(ADR 0011's mock embeddings work offline too, so this runs without a live model).
"""

import math
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher
from itertools import combinations

from pydantic import JsonValue

from agentprobe_core.judges.types import JudgeContext, Judgment, clamp01
from agentprobe_core.suite.judges import ConsistencyJudge


def _text_similarity(a: str, b: str) -> float:
    norm = str.casefold
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _mean_pairwise[T](items: Sequence[T], similarity: Callable[[T, T], float]) -> float:
    pairs = list(combinations(items, 2))
    return sum(similarity(a, b) for a, b in pairs) / len(pairs)


async def consistency(spec: ConsistencyJudge, ctx: JudgeContext) -> Judgment:
    outputs = list(ctx.case_outputs) or [ctx.response.output]
    if len(outputs) < 2:
        return Judgment(
            status="pass",
            score=1.0,
            reason="only one attempt; nothing to compare for consistency",
            evidence={"attempts": len(outputs)},
        )

    text_similarity = _mean_pairwise(outputs, _text_similarity)
    score = text_similarity
    evidence: dict[str, JsonValue] = {
        "attempts": len(outputs),
        "text_similarity": text_similarity,
    }
    if ctx.llm is not None:
        embeddings = (await ctx.llm.embed(outputs)).vectors
        embedding_similarity = clamp01(_mean_pairwise(embeddings, _cosine))
        evidence["embedding_similarity"] = embedding_similarity
        score = (text_similarity + embedding_similarity) / 2

    score = clamp01(score)
    stable = score >= spec.min_agreement
    return Judgment(
        status="pass" if stable else "fail",
        score=score,
        reason=(
            f"stability score {score:.2f} "
            f"{'meets' if stable else 'is below'} min_agreement {spec.min_agreement}"
        ),
        evidence=evidence,
    )
