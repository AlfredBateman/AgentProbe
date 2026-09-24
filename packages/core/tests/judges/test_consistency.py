import pytest

from agentprobe_core.judges.consistency import consistency
from agentprobe_core.suite.judges import ConsistencyJudge
from judgefakes import ScriptedLLM, make_ctx, make_response


async def test_single_attempt_is_trivially_consistent() -> None:
    ctx = make_ctx(response=make_response("only answer"), case_outputs=())
    result = await consistency(ConsistencyJudge(judge="consistency"), ctx)
    assert result.status == "pass"
    assert result.score == 1.0
    assert result.evidence["attempts"] == 1


async def test_identical_outputs_are_fully_consistent() -> None:
    outputs = ("the refund window is 30 days", "the refund window is 30 days")
    ctx = make_ctx(response=make_response(outputs[0]), case_outputs=outputs)
    result = await consistency(ConsistencyJudge(judge="consistency"), ctx)
    assert result.status == "pass"
    assert result.score == pytest.approx(1.0)


async def test_wildly_different_outputs_fail_a_strict_threshold() -> None:
    outputs = ("the refund window is 30 days", "I cannot help you with that request at all")
    ctx = make_ctx(response=make_response(outputs[0]), case_outputs=outputs)
    spec = ConsistencyJudge(judge="consistency", min_agreement=0.95)
    result = await consistency(spec, ctx)
    assert result.status == "fail"
    assert result.score < 0.95


async def test_min_agreement_default_requires_full_agreement() -> None:
    spec = ConsistencyJudge(judge="consistency")
    assert spec.min_agreement == 1.0
    outputs = ("30 days", "45 days")  # the v1/v2 refund-window regression, as text
    ctx = make_ctx(response=make_response(outputs[0]), case_outputs=outputs)
    result = await consistency(spec, ctx)
    assert result.status == "fail"


async def test_embeddings_are_blended_in_when_an_llm_is_given() -> None:
    outputs = ("a", "b", "c")
    llm = ScriptedLLM(embedding_vectors=[[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
    ctx = make_ctx(response=make_response(outputs[0]), case_outputs=outputs, llm=llm)
    result = await consistency(ConsistencyJudge(judge="consistency"), ctx)
    assert result.evidence["embedding_similarity"] == pytest.approx(1.0)
    assert len(llm.embed_calls) == 1
    assert llm.embed_calls[0] == list(outputs)


async def test_orthogonal_embeddings_pull_the_score_down() -> None:
    outputs = ("a", "b")
    llm = ScriptedLLM(embedding_vectors=[[1.0, 0.0], [0.0, 1.0]])
    ctx = make_ctx(response=make_response(outputs[0]), case_outputs=outputs, llm=llm)
    result = await consistency(ConsistencyJudge(judge="consistency"), ctx)
    assert result.evidence["embedding_similarity"] == pytest.approx(0.0)
    # score is the mean of text similarity (identical single chars "a"/"b" -> 0.0) and
    # embedding similarity (0.0), so it should land at 0.0 too.
    assert result.score == pytest.approx(0.0)


async def test_without_an_llm_client_only_text_similarity_is_used() -> None:
    outputs = ("same text", "same text")
    ctx = make_ctx(response=make_response(outputs[0]), case_outputs=outputs, llm=None)
    result = await consistency(ConsistencyJudge(judge="consistency"), ctx)
    assert "embedding_similarity" not in result.evidence
    assert result.score == pytest.approx(1.0)
