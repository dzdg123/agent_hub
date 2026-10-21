import pytest
from research_agent.retrieval import HybridIndex, KeywordIndex, merge_ranked

from research_agent.models import Source


def source(source_id: str, content: str) -> Source:
    return Source(source_id=source_id, title=source_id, content=content)


def test_hybrid_search_finds_chinese_topic():
    index = HybridIndex()
    index.add(
        [
            source("doc-agent", "Agent 由模型、工具、状态和控制流程组成"),
            source("doc-cooking", "西红柿炒鸡蛋需要先准备食材"),
        ]
    )
    results = index.search("Agent 有哪些组成部分", top_k=1)
    assert results[0].source_id == "doc-agent"


def test_merge_ranked_deduplicates_sources():
    first = source("doc-a", "A")
    merged = merge_ranked([[first], [first, source("doc-b", "B")]])
    assert [item.source_id for item in merged] == ["doc-a", "doc-b"]

@pytest.mark.day09_case("K01")
def test_keyword_search_finds_exact_term():
    index = KeywordIndex()
    index.add(
        [
            source("doc-a", "offset 表示文本片段的原始位置"),
            source("doc-b", "max_steps 限制最多执行多少步"),
        ]
    )

    results = index.search("offset")

    assert [item.source_id for item in results] == ["doc-a"]
    assert results[0].score > 0


@pytest.mark.day09_case("K01")
def test_keyword_search_does_not_return_zero_score_results():
    index = KeywordIndex()
    index.add(
        [
            source("doc-a", "offset 表示原始位置"),
            source("doc-b", "model_name 表示模型名称"),
        ]
    )

    assert index.search("completely_unrelated") == []


@pytest.mark.day09_case("K01")
def test_keyword_search_returns_empty_for_blank_query():
    index = KeywordIndex()
    index.add([source("doc-a", "offset")])

    assert index.search("") == []
    assert index.search("   \n\t") == []


@pytest.mark.parametrize(
    "top_k",
    [0, -1, 1.5, "2", True, False],
)
def test_keyword_search_rejects_invalid_top_k(top_k):
    index = KeywordIndex()

    with pytest.raises(ValueError):
        index.search("offset", top_k=top_k)


def test_keyword_search_sorts_ties_by_source_id():
    index = KeywordIndex()
    index.add(
        [
            source("doc-b", "offset"),
            source("doc-a", "offset"),
        ]
    )

    results = index.search("offset")

    assert [item.source_id for item in results] == ["doc-a", "doc-b"]


@pytest.mark.day09_case("S01")
def test_keyword_search_distinguishes_none_and_empty_allowed_ids():
    index = KeywordIndex()
    index.add([source("doc-a", "offset")])

    unrestricted = index.search("offset", allowed_ids=None)
    prohibited = index.search("offset", allowed_ids=set())

    assert [item.source_id for item in unrestricted] == ["doc-a"]
    assert prohibited == []


def test_keyword_search_filters_allowed_ids():
    index = KeywordIndex()
    index.add(
        [
            source("doc-a", "offset"),
            source("doc-b", "offset"),
        ]
    )

    results = index.search(
        "offset",
        allowed_ids={"doc-b"},
    )

    assert [item.source_id for item in results] == ["doc-b"]


def test_keyword_search_does_not_modify_original_source():
    original = Source(
        source_id="doc-a",
        title="A",
        content="offset",
        metadata={"location": {"offset": 12}},
    )
    index = KeywordIndex()
    index.add([original])

    result = index.search("offset")[0]
    result.metadata["location"]["offset"] = 99

    assert original.score == 0.0
    assert original.metadata["location"]["offset"] == 12

