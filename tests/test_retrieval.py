from research_agent.models import Source
from research_agent.retrieval import HybridIndex, merge_ranked


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

