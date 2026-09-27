"""Failure clustering (ADR 0024): the clustering algorithm on its own, then `cluster_failures`
end to end against `ScriptedLLM` for exact control over embeddings and the summarizer's
response.
"""

from agentprobe_core.findings import (
    ClusterFinding,
    FailingOutput,
    agglomerative_cluster,
    cluster_failures,
    cosine_distance,
)
from agentprobe_core.llm.types import Completion
from judgefakes import ScriptedLLM


def test_cosine_distance_of_identical_vectors_is_zero() -> None:
    assert cosine_distance([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_distance_of_orthogonal_vectors_is_one() -> None:
    assert cosine_distance([1.0, 0.0], [0.0, 1.0]) == 1.0


def test_cosine_distance_of_a_zero_vector_is_maximal() -> None:
    assert cosine_distance([0.0, 0.0], [1.0, 2.0]) == 1.0


def test_agglomerative_cluster_of_no_vectors_is_no_clusters() -> None:
    assert agglomerative_cluster([]) == []


def test_agglomerative_cluster_of_one_vector_is_one_cluster() -> None:
    assert agglomerative_cluster([[1.0, 0.0]]) == [[0]]


def test_agglomerative_cluster_merges_identical_vectors() -> None:
    vectors = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    assert agglomerative_cluster(vectors) == [[0, 1, 2]]


def test_agglomerative_cluster_keeps_unrelated_vectors_apart() -> None:
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    assert agglomerative_cluster(vectors) == [[0], [1]]


def test_agglomerative_cluster_groups_near_vectors_and_leaves_a_far_one_out() -> None:
    # 0 and 1 are near-identical; 2 points somewhere else entirely.
    vectors = [[1.0, 0.01], [1.0, 0.0], [0.0, 1.0]]
    clusters = agglomerative_cluster(vectors, threshold=0.05)
    assert sorted(clusters) == [[0, 1], [2]]


def test_agglomerative_cluster_is_deterministic_regardless_of_input_order() -> None:
    vectors = [[1.0, 0.0], [0.99, 0.01], [0.0, 1.0], [0.01, 0.99]]
    first = agglomerative_cluster(vectors, threshold=0.05)
    reordered = [vectors[3], vectors[1], vectors[0], vectors[2]]
    second = agglomerative_cluster(reordered, threshold=0.05)

    # Same grouping by original content, however the input happened to be ordered.
    def as_sets(
        clusters: list[list[int]], vs: list[list[float]]
    ) -> list[tuple[tuple[float, ...], ...]]:
        return sorted(tuple(sorted(tuple(vs[i]) for i in c)) for c in clusters)

    assert as_sets(first, vectors) == as_sets(second, reordered)


async def test_cluster_failures_of_nothing_is_nothing() -> None:
    assert await cluster_failures([], ScriptedLLM()) == []


async def test_cluster_failures_of_one_item_is_one_finding() -> None:
    llm = ScriptedLLM(
        embedding_vectors=[[1.0, 0.0]],
        completions=[Completion(text="Summary: leaks a secret\nFix: redact it", model="mock")],
    )
    findings = await cluster_failures([FailingOutput(result_id="r1", text="the secret is X")], llm)
    assert findings == [
        ClusterFinding(
            label="leaks a secret",
            summary="leaks a secret",
            suggested_fix="redact it",
            member_result_ids=["r1"],
            embedding=[1.0, 0.0],
        )
    ]


async def test_cluster_failures_groups_identical_outputs_into_one_cluster() -> None:
    llm = ScriptedLLM(
        embedding_vectors=[[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]],
        completions=[
            Completion(text="Summary: same failure every time\nFix: fix it", model="mock")
        ],
    )
    items = [FailingOutput(result_id=f"r{i}", text="identical output") for i in range(3)]
    findings = await cluster_failures(items, llm)
    assert len(findings) == 1
    assert findings[0].member_result_ids == ["r0", "r1", "r2"]
    assert findings[0].embedding == [1.0, 0.0]  # the centroid of three identical vectors


async def test_cluster_failures_keeps_unrelated_failures_in_separate_clusters() -> None:
    llm = ScriptedLLM(
        embedding_vectors=[[1.0, 0.0], [0.0, 1.0]],
        completions=[
            Completion(text="Summary: first problem\nFix: fix one", model="mock"),
            Completion(text="Summary: second problem\nFix: fix two", model="mock"),
        ],
    )
    items = [
        FailingOutput(result_id="r1", text="leaks the API key"),
        FailingOutput(result_id="r2", text="writes a poem instead of answering"),
    ]
    findings = await cluster_failures(items, llm)
    assert len(findings) == 2
    assert {f.member_result_ids[0] for f in findings} == {"r1", "r2"}
    assert {f.summary for f in findings} == {"first problem", "second problem"}


async def test_cluster_failures_falls_back_when_the_summary_has_no_format() -> None:
    llm = ScriptedLLM(
        embedding_vectors=[[1.0, 0.0]],
        completions=[Completion(text="mock summarizer response abc123", model="mock")],
    )
    findings = await cluster_failures([FailingOutput(result_id="r1", text="whatever")], llm)
    assert findings[0].summary == "mock summarizer response abc123"
    assert findings[0].suggested_fix  # the generic fallback, not empty
    assert findings[0].label == "mock summarizer response abc123"


async def test_cluster_failures_truncates_a_long_label() -> None:
    long_summary = "root cause " * 20
    llm = ScriptedLLM(
        embedding_vectors=[[1.0, 0.0]],
        completions=[Completion(text=f"Summary: {long_summary}\nFix: shorten it", model="mock")],
    )
    findings = await cluster_failures([FailingOutput(result_id="r1", text="x")], llm)
    assert len(findings[0].label) == 60
    assert findings[0].label.endswith("…")
    assert findings[0].summary == long_summary.strip()


async def test_cluster_failures_sends_the_summarizer_role_and_grouped_text() -> None:
    llm = ScriptedLLM(
        embedding_vectors=[[1.0, 0.0], [1.0, 0.0]],
        completions=[Completion(text="Summary: s\nFix: f", model="mock")],
    )
    items = [
        FailingOutput(result_id="r1", text="alpha output"),
        FailingOutput(result_id="r2", text="alpha output"),
    ]
    await cluster_failures(items, llm)
    assert len(llm.embed_calls) == 1
    assert llm.embed_calls[0] == ["alpha output", "alpha output"]
    assert len(llm.complete_calls) == 1
    user_message = llm.complete_calls[0][1]["content"]
    assert "2 failing outputs" in user_message
    assert "alpha output" in user_message
