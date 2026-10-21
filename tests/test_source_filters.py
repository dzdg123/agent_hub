from copy import deepcopy

import pytest

from research_agent.models import Source
from research_agent.retrieval import ChromaIndex, KeywordIndex
from research_agent.retrieval_pipeline import TwoBranchRetriever
from research_agent.source_filters import normalize_filters, resolve_allowed_ids


def sources():
    return [
        Source(source_id="txt", title="txt", content="offset", metadata={
            "file_type": "txt", "relative_path": "notes/readme.txt"}),
        Source(source_id="md", title="md", content="offset", metadata={
            "file_type": "markdown", "relative_path": "notes/readme.md"}),
        Source(source_id="pdf-1", title="pdf1", content="offset", page=1, metadata={
            "file_type": "pdf", "relative_path": "guide.pdf"}),
        Source(source_id="pdf-2", title="pdf2", content="offset", page=2, metadata={
            "file_type": "pdf", "relative_path": "guide.pdf"}),
        Source(source_id="other", title="other", content="offset", metadata={
            "file_type": "pdf", "relative_path": "other/guide.pdf"}),
    ]


@pytest.mark.day09_case("S01", "S03")
def test_resolver_none_empty_or_and_and_multiple_chunks():
    canonical = sources()
    assert resolve_allowed_ids(canonical) is None
    assert resolve_allowed_ids(canonical, {}) is None
    assert resolve_allowed_ids(canonical, {"file_types": set()}) == set()
    assert resolve_allowed_ids(canonical, {"relative_paths": set()}) == set()
    assert resolve_allowed_ids([], {"file_types": {"pdf"}}) == set()
    assert resolve_allowed_ids(canonical, {"file_types": {"txt", "markdown"}}) == {"txt", "md"}
    assert resolve_allowed_ids(canonical, {"relative_paths": {"guide.pdf"}}) == {"pdf-1", "pdf-2"}
    assert resolve_allowed_ids(canonical, {
        "file_types": {"pdf"}, "relative_paths": {"notes/readme.txt", "guide.pdf"},
    }) == {"pdf-1", "pdf-2"}
    assert resolve_allowed_ids(canonical, {"relative_paths": {"missing.pdf"}}) == set()
    assert resolve_allowed_ids(canonical, {
        "file_types": {"txt"}, "relative_paths": {"guide.pdf"},
    }) == set()


def test_normalization_is_independent_and_runtime_fields_cannot_widen_scope():
    canonical = sources()
    filters = {"file_types": {" PDF "}, "relative_paths": {"notes\\readme.md"}}
    before_sources, before_filters = deepcopy(canonical), deepcopy(filters)
    normalized = normalize_filters(filters)
    assert normalized == {"file_types": {"pdf"}, "relative_paths": {"notes/readme.md"}}
    normalized["file_types"].add("txt")
    assert filters == before_filters
    assert canonical == before_sources
    canonical[0].metadata["_retrieval"] = {"file_type": "pdf", "relative_path": "guide.pdf"}
    assert "txt" not in resolve_allowed_ids(canonical, {"file_types": {"pdf"}})
    # 不猜测缺失字段，也不使用绝对 file_path 冒充 metadata.relative_path。
    missing = Source(source_id="missing", title="?", content="offset", file_path="guide.pdf")
    assert resolve_allowed_ids([missing], {"relative_paths": {"guide.pdf"}}) == set()


@pytest.mark.parametrize("filters,error", [
    ({"unknown": {"pdf"}}, ValueError), ({"file_types": {"docx"}}, ValueError),
    ({"file_types": "pdf"}, TypeError), ({"file_types": ["pdf"]}, TypeError),
    ({"file_types": {1}}, TypeError), ({"relative_paths": None}, TypeError),
    ({"relative_paths": {"../guide.pdf"}}, ValueError),
    ({"relative_paths": {"/guide.pdf"}}, ValueError),
    ({"relative_paths": {"C:\\guide.pdf"}}, ValueError),
    ({"relative_paths": {""}}, ValueError), ({"relative_paths": {"."}}, ValueError),
    ([], TypeError),
])
@pytest.mark.day09_case("S03")
def test_invalid_filters_are_rejected_even_for_empty_query(filters, error):
    with pytest.raises(error):
        resolve_allowed_ids([], filters)
    keyword, vector = KeywordIndex(), KeywordIndex()
    retriever = TwoBranchRetriever([], keyword_index=keyword, vector_index=vector)
    with pytest.raises(error):
        retriever.search("", filters=filters)


def test_explicit_id_limit_and_filters_intersect_and_diagnostics_are_snapshots():
    canonical = sources()
    keyword, vector = KeywordIndex(), KeywordIndex()
    keyword.add(canonical)
    vector.add(canonical)
    retriever = TwoBranchRetriever(canonical, keyword_index=keyword, vector_index=vector)
    filters, allowed = {"file_types": {"pdf"}}, {"txt", "pdf-2"}
    result = retriever.search("offset", filters=filters, allowed_ids=allowed)
    assert result.allowed_source_count == result.effective_candidate_k == 1
    assert [source.source_id for source in result.final_sources] == ["pdf-2"]
    assert result.filters == {"file_types": ["pdf"]}
    assert result.requested_allowed_ids == ["pdf-2", "txt"]
    filters["file_types"].add("txt")
    allowed.add("pdf-1")
    assert result.filters == {"file_types": ["pdf"]}
    assert result.requested_allowed_ids == ["pdf-2", "txt"]
    assert retriever.search("offset", filters={"file_types": {"pdf"}}, allowed_ids=set()).final_sources == []


@pytest.mark.day09_case("S02", "S03")
def test_real_chroma_filter_before_candidate_cutoff_and_final_rrf(tmp_path, monkeypatch):
    from research_agent.context import build_context

    pytest.importorskip("chromadb")

    class Embedder:
        def __init__(self):
            self.query_count = 0

        def embed_documents(self, texts):
            return [[1, 0], [0.99, 0.01], [0.98, 0.02], [0, 1], [-0.1, 1]]

        def embed_query(self, query):
            self.query_count += 1
            return [1, 0]

    canonical = [Source(
        source_id=f"doc-{i}", title=str(i), content="offset" if i < 3 else f"offset guide page_{i}",
        file_path=f"text-{i}.txt" if i < 3 else "guide.pdf",
        page=None if i < 3 else i - 2,
        metadata={"file_type": "txt" if i < 3 else "pdf",
                  "relative_path": f"text-{i}.txt" if i < 3 else "guide.pdf"},
    ) for i in range(5)]
    before = deepcopy(canonical)
    embedder = Embedder()
    keyword = KeywordIndex()
    vector = ChromaIndex(tmp_path / "chroma", collection_name="stage-four-test", embedder=embedder)
    keyword.add(canonical)
    vector.add(canonical)
    for index in (keyword, vector):
        assert {hit.source_id for hit in index.search("offset", top_k=3)} == {"doc-0", "doc-1", "doc-2"}
        assert index.search("offset", top_k=5)[3].source_id == "doc-3"
    captured = []
    original = type(vector.collection).query

    def capture(collection, *args, **kwargs):
        captured.append(kwargs)
        return original(collection, *args, **kwargs)

    monkeypatch.setattr(type(vector.collection), "query", capture)
    retriever = TwoBranchRetriever(canonical, keyword_index=keyword, vector_index=vector)
    result = retriever.search("offset", filters={"file_types": {"pdf"}, "relative_paths": {"guide.pdf"}})
    assert result.total_source_count == 5
    assert result.allowed_source_count == result.effective_candidate_k == 2
    assert captured[0]["n_results"] == 2
    assert captured[0]["where"] == {"filter_source_id": {"$in": ["doc-3", "doc-4"]}}
    assert {hit.source_id for hit in result.final_sources} == {"doc-3", "doc-4"}
    for branch in result.branches.values():
        assert {hit.source_id for hit in branch.sources} == {"doc-3", "doc-4"}
        assert all(hit.metadata["file_type"] == "pdf" for hit in branch.sources)
    assert all(hit.metadata["file_type"] == "pdf" for hit in result.final_sources)
    context = build_context(result.final_sources)
    assert set(context.included_source_ids) == {"doc-3", "doc-4"}
    assert all(f'[source_id: "doc-{i}"]' not in context.text for i in range(3))
    assert context.used_chars == len(context.text) <= context.budget
    assert '文件："guide.pdf"' in context.text
    assert canonical == before
    query_count = embedder.query_count
    empty = retriever.search("offset", filters={"relative_paths": {"missing.pdf"}})
    assert empty.allowed_source_count == empty.final_count == 0
    assert empty.final_sources == []
    assert build_context(empty.final_sources).status == "empty_input"
    assert all(branch.status == "skipped" for branch in empty.branches.values())
    assert embedder.query_count == query_count
    assert len(captured) == 1  # 无匹配范围不能向数据库发出不受限的第二次查询。


@pytest.mark.day09_case("S01")
def test_real_chroma_none_is_unrestricted_but_empty_ids_do_not_query_or_embed(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")

    class Embedder:
        def __init__(self): self.query_calls = 0
        def embed_documents(self, texts): return [[1, 0] for _ in texts]
        def embed_query(self, query):
            self.query_calls += 1
            return [1, 0]

    embedder = Embedder()
    index = ChromaIndex(tmp_path / "chroma", embedder=embedder)
    index.add([Source(source_id="doc-a", title="A", content="offset")])
    captured = []
    query = type(index.collection).query

    def capture(collection, *args, **kwargs):
        captured.append(kwargs)
        return query(collection, *args, **kwargs)

    monkeypatch.setattr(type(index.collection), "query", capture)
    assert [source.source_id for source in index.search("offset", allowed_ids=None)] == ["doc-a"]
    assert len(captured) == embedder.query_calls == 1
    assert "where" not in captured[0]
    assert index.search("offset", allowed_ids=set()) == []
    assert len(captured) == embedder.query_calls == 1


def test_cli_accepts_file_filter_and_fuses_empty_range(tmp_path, monkeypatch, capsys):
    pytest.importorskip("chromadb")
    import json
    from examples.day09_candidates import main

    monkeypatch.setattr("sys.argv", ["day09_candidates.py", "--smoke", "--fuse",
                                    "--relative-path", "missing.pdf", "--output-root", str(tmp_path)])
    main()
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["filters"] == {"relative_paths": ["missing.pdf"]}
    assert result["allowed_source_count"] == result["final_count"] == 0
    assert result["final_sources"] == []
