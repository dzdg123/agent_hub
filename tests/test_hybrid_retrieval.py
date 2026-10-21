"""阶段二：共同来源、候选契约与真实 Chroma 过滤路径。"""

from dataclasses import asdict

import pytest

from research_agent.models import Source
from research_agent.retrieval import KeywordIndex, IndexDataError
from research_agent.retrieval_pipeline import TwoBranchRetriever


class RecordingIndex(KeywordIndex):
    def __init__(self):
        super().__init__()
        self.calls = []

    def search(self, query, top_k=5, *, allowed_ids=None):
        self.calls.append((query, top_k, allowed_ids))
        return super().search(query, top_k, allowed_ids=allowed_ids)


def make_retriever(count=4):
    sources = [
        Source(source_id=f"doc-{i}", title=str(i), content="offset",
               metadata={"nested": {"offset": i}})
        for i in range(count)
    ]
    keyword, vector = RecordingIndex(), RecordingIndex()
    keyword.add(sources)
    vector.add(sources)
    return sources, keyword, vector, TwoBranchRetriever(
        sources, keyword_index=keyword, vector_index=vector,
    )


def test_candidate_limit_is_distinct_from_final_top_k_and_traces_are_independent():
    sources, keyword, vector, retriever = make_retriever(8)
    result = retriever.retrieve_candidates("offset", candidate_k=6, top_k=3)
    assert result.requested_top_k == 3
    assert result.final_sources is None and result.final_count is None
    assert result.degraded_reason is None
    for name, branch in result.branches.items():
        assert branch.status == "ok"
        assert branch.candidate_count == 6
        assert branch.elapsed_ms >= 0
        assert [trace.rank for trace in branch.traces] == list(range(1, 7))
        assert all(trace.branch == name and trace.raw_score == 1 for trace in branch.traces)
        assert all(trace.fusion_contribution is None for trace in branch.traces)
    result.branches["keyword"].sources[0].metadata["nested"]["offset"] = 999
    assert sources[0].metadata["nested"]["offset"] == 0
    assert result.branches["vector"].sources[0].metadata["nested"]["offset"] == 0
    assert keyword.all()[0].metadata["nested"]["offset"] == 0
    assert "branches" in asdict(result)


def test_allowed_range_caps_candidate_k_before_both_queries():
    _, keyword, vector, retriever = make_retriever()
    result = retriever.retrieve_candidates("offset", allowed_ids={"doc-3", "unknown"})
    assert result.total_source_count == 4
    assert result.allowed_source_count == result.effective_candidate_k == 1
    for index in (keyword, vector):
        assert index.calls == [("offset", 1, {"doc-3"})]
    assert result.branches["keyword"].candidate_count == 1


@pytest.mark.parametrize("query,allowed,reason", [
    ("offset", set(), "no_allowed_sources"),
    ("offset", {"unknown"}, "no_allowed_sources"),
    (" \n\t", None, "blank_query"),
])
def test_skipped_queries_do_not_call_branches(query, allowed, reason):
    _, keyword, vector, retriever = make_retriever()
    result = retriever.retrieve_candidates(query, allowed_ids=allowed)
    assert keyword.calls == vector.calls == []
    assert all(branch.status == "skipped" and branch.skip_reason == reason
               for branch in result.branches.values())


@pytest.mark.parametrize("kwargs", [
    {"candidate_k": True}, {"candidate_k": 0}, {"candidate_k": 1.5},
    {"top_k": False}, {"top_k": -1}, {"top_k": "3"},
    {"candidate_k": 2, "top_k": 3},
])
def test_invalid_parameters_fail_even_for_blank_query(kwargs):
    _, keyword, vector, retriever = make_retriever()
    with pytest.raises(ValueError):
        retriever.retrieve_candidates("", **kwargs)
    assert keyword.calls == vector.calls == []


def test_empty_corpus_and_no_keyword_match():
    _, _, _, empty = make_retriever(0)
    assert empty.retrieve_candidates("offset").effective_candidate_k == 0
    _, _, _, retriever = make_retriever()
    result = retriever.retrieve_candidates("unrelated")
    assert result.branches["keyword"].status == "empty"


def test_search_fuses_candidates_fills_final_fields_and_branch_contributions():
    sources, keyword, vector, retriever = make_retriever(8)
    result = retriever.search("offset", candidate_k=6, top_k=3)
    assert result.final_count == 3
    assert [source.source_id for source in result.final_sources] == ["doc-0", "doc-1", "doc-2"]
    assert len(keyword.calls) == len(vector.calls) == 1
    assert result.final_sources[0].score == pytest.approx(2 / 61)
    assert len(result.fusion.traces) == 12
    assert result.branches["keyword"].traces[0].fusion_contribution == pytest.approx(1 / 61)
    result.final_sources[0].metadata["nested"]["offset"] = 999
    assert result.fusion.sources[0].metadata["nested"]["offset"] == 0
    assert sources[0].metadata["nested"]["offset"] == 0
    assert retriever.search("offset", allowed_ids=set()).final_sources == []
    with pytest.raises(ValueError, match="rank_constant"):
        retriever.search("", rank_constant=True)


def test_stale_or_changed_index_is_rejected():
    sources, keyword, vector, retriever = make_retriever()
    changed = sources[0].model_copy(update={"content": "changed"})
    vector.add([changed])
    with pytest.raises(IndexDataError, match="冲突"):
        retriever.retrieve_candidates("offset")
    vector.add([sources[0], Source(source_id="old", title="old", content="old")])
    with pytest.raises(IndexDataError, match="ID 集合"):
        TwoBranchRetriever(sources, keyword_index=keyword, vector_index=vector)


def test_query_results_are_not_canonical_sources_and_errors_propagate():
    sources, keyword, vector, retriever = make_retriever()
    queried = sources[0].model_copy(deep=True)
    queried.metadata["_retrieval"] = {"metric": "cosine"}
    with pytest.raises(IndexDataError, match="运行时"):
        TwoBranchRetriever([queried], keyword_index=keyword, vector_index=vector)

    def fail(*args, **kwargs):
        raise OSError("vector unavailable")

    vector.search = fail
    with pytest.raises(OSError, match="vector unavailable"):
        retriever.retrieve_candidates("offset")


def test_filter_before_top_k_with_real_chroma_and_controlled_embedder(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from research_agent.retrieval import ChromaIndex, IndexConfigurationError

    class Embedder:
        def __init__(self):
            self.query_calls = []

        def embed_documents(self, texts):
            return [[1, 0], [0.9, 0.1], [0.8, 0.2], [0, 1]][:len(texts)]

        def embed_query(self, text):
            self.query_calls.append(text)
            return [1, 0]

    sources = [Source(source_id=f"doc-{i}", title=str(i), content=f"offset text_{i}",
                      file_path=f"doc.{('pdf' if i == 3 else 'txt')}") for i in range(4)]
    embedder = Embedder()
    vector = ChromaIndex(tmp_path / "chroma", embedder=embedder)
    vector.add(sources)
    keyword = KeywordIndex()
    keyword.add(sources)
    assert "doc-3" not in [hit.source_id for hit in vector.search("offset", top_k=3)]
    captured = []
    original_query = type(vector.collection).query

    def capture(collection, *args, **kwargs):
        captured.append(kwargs)
        return original_query(collection, *args, **kwargs)

    monkeypatch.setattr(type(vector.collection), "query", capture)
    retriever = TwoBranchRetriever(sources, keyword_index=keyword, vector_index=vector)
    result = retriever.retrieve_candidates("offset", allowed_ids={"doc-3"})
    assert captured[0]["where"] == {"filter_source_id": {"$in": ["doc-3"]}}
    assert captured[0]["n_results"] == 1
    for branch in result.branches.values():
        assert [hit.source_id for hit in branch.sources] == ["doc-3"]
    trace = result.branches["vector"].traces[0]
    assert trace.metric == "embedding_cosine"
    assert trace.raw_score == pytest.approx(0)
    assert trace.distance == pytest.approx(1)
    calls = len(embedder.query_calls)
    assert vector.search("offset", allowed_ids=set()) == []
    assert vector.search("offset", allowed_ids={"missing"}) == []
    assert len(embedder.query_calls) == calls
    hit = result.branches["vector"].sources[0]
    with pytest.raises(ValueError, match="保留检索字段"):
        vector.add([hit])
    # 模拟旧集合：未写入过滤字段时，拒绝悄悄漏掉允许文档。
    vector.collection.update(ids=["doc-3"], metadatas=[{"filter_source_id": "legacy"}])
    with pytest.raises(IndexConfigurationError, match="新的 Day 09"):
        vector.search("offset", allowed_ids={"doc-3"})


def test_smoke_demo_serializes_sources_and_preserves_output(tmp_path, monkeypatch, capsys):
    pytest.importorskip("chromadb")
    import json
    from examples.day09_candidates import main

    monkeypatch.setattr("sys.argv", [
        "day09_candidates.py", "--smoke", "--allowed-id", "doc-offset",
        "--output-root", str(tmp_path / "runs"),
    ])
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "smoke_controlled_vectors_not_semantic_evaluation"
    for branch in payload["result"]["branches"].values():
        assert branch["sources"][0]["source_id"] == "doc-offset"
    assert len(list((tmp_path / "runs").glob("*/candidates.json"))) == 1
