import json
import sqlite3
import sys
from copy import deepcopy
from types import ModuleType

import pytest

from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.models import Source
from research_agent.retrieval import ChromaIndex, IndexConfigurationError, IndexDataError, KeywordIndex
from research_agent.retrieval_errors import RetrievalOperationalError, operational_boundary
from research_agent.retrieval_pipeline import LazyCandidateIndex, TwoBranchRetriever


class FaultIndex(KeywordIndex):
    def __init__(self, sources):
        super().__init__()
        self.add(sources)
        self.fault = None
        self.read_fault = None
        self.empty = False
        self.calls = 0

    def all(self):
        if self.read_fault:
            raise self.read_fault
        return super().all()

    def search(self, query, top_k=5, *, allowed_ids=None):
        self.calls += 1
        if self.fault:
            raise self.fault
        return [] if self.empty else super().search(query, top_k, allowed_ids=allowed_ids)


def setup():
    sources = [Source(source_id="A", title="A", content="offset",
                      metadata={"nested": {"key": "value"}})]
    keyword, vector = FaultIndex(sources), FaultIndex(sources)
    retriever = TwoBranchRetriever(sources, keyword_index=keyword, vector_index=vector)
    return sources, keyword, vector, retriever


@pytest.mark.parametrize("failed", ["keyword", "vector"])
@pytest.mark.parametrize("allow", [False, True])
def test_single_failure_requires_explicit_permission_and_keeps_diagnostics(failed, allow, monkeypatch):
    sources, keyword, vector, retriever = setup()
    before = deepcopy(sources)
    indexes = {"keyword": keyword, "vector": vector}
    indexes[failed].fault = RetrievalOperationalError("暂时不可用", error_type="TimeoutError")
    ticks = iter(range(20))
    monkeypatch.setattr("research_agent.retrieval_pipeline.perf_counter", lambda: next(ticks))
    result = retriever.search("offset", allow_degraded=allow, query_id="q-007")
    assert result.query_id == "q-007"
    assert result.allow_degraded is allow
    assert keyword.calls == vector.calls == 1
    branch = result.branches[failed]
    assert branch.status == "failed" and branch.candidate_count is None
    assert branch.error_type == "TimeoutError"
    assert branch.error_message == "暂时不可用"
    assert branch.failure_stage == "search"
    assert branch.elapsed_ms > 0
    assert branch.sources == branch.traces == []
    assert result.status == ("degraded" if allow else "failed")
    if allow:
        assert result.degraded_reason
        assert result.failure_reason is None
        assert result.final_count == 1
        assert result.final_sources[0].score == pytest.approx(1 / 61)
        assert {trace.branch for trace in result.fusion.traces} == ({"keyword", "vector"} - {failed})
        result.final_sources[0].metadata["nested"]["key"] = "changed"
    else:
        assert result.final_sources is result.final_count is result.fusion is None
        assert result.failure_reason and result.degraded_reason is None
    assert sources == before


@pytest.mark.day09_case("E02")
def test_default_strict_and_both_failed_even_when_degradation_allowed():
    _, keyword, vector, retriever = setup()
    vector.fault = RetrievalOperationalError("vector failure")
    assert retriever.search("offset").status == "failed"
    keyword.fault = RetrievalOperationalError("keyword failure")
    result = retriever.search("offset", allow_degraded=True)
    assert result.status == "failed"
    assert "两路均失败" in result.failure_reason
    assert result.final_sources is result.final_count is result.fusion is None
    assert all(branch.status == "failed" and branch.candidate_count is None
               and branch.error_type and branch.error_message for branch in result.branches.values())


@pytest.mark.day09_case("E02")
def test_empty_is_success_and_is_distinct_from_failure():
    _, keyword, vector, retriever = setup()
    vector.empty = True
    result = retriever.search("offset")
    assert result.status == "ok" and result.final_count == 1
    assert result.branches["vector"].status == "empty"
    assert result.branches["vector"].candidate_count == 0
    assert result.degraded_reason is None
    keyword.empty = True
    empty = retriever.search("offset")
    assert empty.status == "empty" and empty.final_sources == []
    assert empty.final_count == 0 and empty.fusion is not None
    assert empty.failure_reason is empty.degraded_reason is None
    assert all(branch.candidate_count == 0 and branch.error_type is None
               for branch in empty.branches.values())
    vector.fault = RetrievalOperationalError("failure")
    result = retriever.search("offset", allow_degraded=True)
    assert result.status == "degraded" and result.final_sources == []
    assert result.degraded_reason


@pytest.mark.day09_case("E01")
@pytest.mark.parametrize("failed_name", ["keyword", "vector"])
def test_degraded_result_keeps_intersection_of_filters_and_explicit_allowed_ids(failed_name, monkeypatch):
    from research_agent.context import build_context

    canonical = [
        Source(source_id="txt", title="TXT", content="offset", file_path="notes.txt",
               metadata={"file_type": "txt", "relative_path": "notes.txt"}),
        Source(source_id="pdf-1", title="PDF page1", content="offset", file_path="guide.pdf", page=1,
               metadata={"file_type": "pdf", "relative_path": "guide.pdf"}),
        Source(source_id="pdf-2", title="PDF page2", content="offset", file_path="guide.pdf", page=2,
               metadata={"file_type": "pdf", "relative_path": "guide.pdf"}),
    ]
    before = deepcopy(canonical)
    indexes = {name: FaultIndex(canonical) for name in ("keyword", "vector")}
    retriever = TwoBranchRetriever(canonical, keyword_index=indexes["keyword"], vector_index=indexes["vector"])
    indexes[failed_name].fault = RetrievalOperationalError("timeout", error_type="TimeoutError")
    captured = {}
    for name, index in indexes.items():
        original = index.search
        def capture(query, top_k=5, *, allowed_ids=None, branch=name, search=original):
            captured[branch] = (top_k, allowed_ids)
            return search(query, top_k, allowed_ids=allowed_ids)
        monkeypatch.setattr(index, "search", capture)
    result = retriever.search(
        "offset", allow_degraded=True, query_id="E01-filtered",
        filters={"file_types": {"pdf"}, "relative_paths": {"guide.pdf"}},
        allowed_ids={"txt", "pdf-2"},
    )
    assert result.status == "degraded" and result.degraded_reason
    assert result.query_id == "E01-filtered"
    assert result.allowed_source_count == result.effective_candidate_k == 1
    assert captured == {"keyword": (1, {"pdf-2"}), "vector": (1, {"pdf-2"})}
    failed = result.branches[failed_name]
    assert failed.status == "failed" and failed.candidate_count is None
    assert failed.error_type == "TimeoutError" and failed.failure_stage == "search"
    assert failed.elapsed_ms >= 0
    assert [source.source_id for source in result.final_sources] == ["pdf-2"]
    assert result.final_sources[0].score == pytest.approx(1 / 61)
    assert {trace.branch for trace in result.fusion.traces} == {"keyword", "vector"} - {failed_name}
    context = build_context(result.final_sources)
    assert context.included_source_ids == ["pdf-2"]
    assert '文件："guide.pdf"' in context.text and "物理页：2" in context.text
    assert 'source_id: "txt"' not in context.text
    assert canonical == before


@pytest.mark.parametrize("error", [
    IndexDataError("冲突"), IndexConfigurationError("配置错误"),
    TypeError("bug"), AttributeError("bug"), ValueError("invalid"),
    RuntimeError("unclassified"), OSError("unadapted"),
])
def test_unclassified_program_data_and_configuration_errors_propagate(error):
    _, keyword, vector, retriever = setup()
    keyword.fault = RetrievalOperationalError("first failed")
    vector.fault = error
    with pytest.raises(type(error), match=str(error)):
        retriever.search("offset", allow_degraded=True)


def test_illegal_filters_are_rejected_before_search_even_when_failure_is_configured():
    _, keyword, vector, retriever = setup()
    vector.fault = RetrievalOperationalError("failed")
    with pytest.raises(ValueError):
        retriever.search("offset", filters={"unknown": {"pdf"}}, allow_degraded=True)
    assert keyword.calls == vector.calls == 0


def test_conflicting_sources_cannot_be_bypassed_by_a_failed_other_branch():
    sources, keyword, vector, retriever = setup()
    keyword.fault = RetrievalOperationalError("unavailable")
    vector.add([sources[0].model_copy(update={"content": "different"})])
    with pytest.raises(IndexDataError, match="冲突"):
        retriever.search("offset", allow_degraded=True)


@pytest.mark.parametrize("query,allowed", [("  ", None), ("offset", set())])
def test_skipped_is_not_failure_and_does_not_initialize(query, allowed):
    _, keyword, _, _ = setup()
    def must_not_initialize():
        raise AssertionError("should not initialize")
    retriever = TwoBranchRetriever(keyword.all(), keyword_index=keyword,
                                  vector_index=LazyCandidateIndex(must_not_initialize))
    result = retriever.search(query, allowed_ids=allowed, allow_degraded=True)
    assert result.status == "skipped" and result.final_sources == []
    assert keyword.calls == 0
    assert all(branch.status == "skipped" for branch in result.branches.values())


def test_read_failure_is_recorded_and_rechecked_on_the_next_request():
    _, _, vector, retriever = setup()
    vector.read_fault = RetrievalOperationalError("read unavailable")
    result = retriever.search("offset", allow_degraded=True)
    assert result.status == "degraded"
    assert result.branches["vector"].failure_stage == "validation_read"
    assert vector.calls == 0
    vector.read_fault = None
    assert retriever.search("offset").status == "ok"


def test_lazy_initialization_failure_retries_without_caching_failure():
    sources, keyword, vector, _ = setup()
    calls = []
    def factory():
        calls.append(1)
        if len(calls) == 1:
            with operational_boundary("模型加载"):
                raise OSError("model missing")
        return vector
    retriever = TwoBranchRetriever(sources, keyword_index=keyword,
                                  vector_index=LazyCandidateIndex(factory))
    assert calls == []
    failed = retriever.search("offset", allow_degraded=True)
    assert failed.branches["vector"].failure_stage == "initialization"
    assert failed.branches["vector"].error_type == "OSError"
    assert retriever.search("offset").status == "ok"
    assert retriever.search("offset").status == "ok"
    assert len(calls) == 2


@pytest.mark.parametrize("kwargs,error", [
    ({"allow_degraded": 1}, TypeError), ({"allow_degraded": "true"}, TypeError),
    ({"query_id": " "}, ValueError), ({"query_id": 7}, ValueError),
])
def test_new_parameters_are_validated_even_for_blank_query(kwargs, error):
    _, _, _, retriever = setup()
    with pytest.raises(error):
        retriever.search("", **kwargs)


def test_candidate_mode_has_status_but_does_not_fuse_and_generates_query_ids():
    _, _, vector, retriever = setup()
    vector.fault = RetrievalOperationalError("unavailable")
    result = retriever.retrieve_candidates("offset", allow_degraded=True)
    assert result.status == "degraded"
    assert result.final_sources is result.final_count is result.fusion is None
    assert result.query_id and retriever.search("offset").query_id != result.query_id


def test_operational_boundary_preserves_cause_and_rejects_unclassified_sqlite_errors():
    cause = TimeoutError("offline")
    with pytest.raises(RetrievalOperationalError) as error:
        with operational_boundary("test"):
            raise cause
    assert error.value.__cause__ is cause
    assert error.value.error_type == "TimeoutError"
    for code in [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_CORRUPT]:
        cause = sqlite3.OperationalError("database issue")
        cause.sqlite_errorcode = code
        expected = sqlite3.OperationalError if code == sqlite3.SQLITE_CORRUPT else RetrievalOperationalError
        with pytest.raises(expected):
            with operational_boundary("database"):
                raise cause


@pytest.mark.parametrize("error", [OSError("offline"), TypeError("model bug"), RuntimeError("unknown")])
def test_model_initialization_only_wraps_known_errors(monkeypatch, error):
    module = ModuleType("sentence_transformers")
    def unavailable(*args, **kwargs):
        raise error
    module.SentenceTransformer = unavailable
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    expected = RetrievalOperationalError if isinstance(error, OSError) else type(error)
    with pytest.raises(expected):
        SentenceTransformerEmbedder()


def test_model_encode_io_error_keeps_cause_but_invalid_output_stays_fatal():
    class Model:
        max_seq_length = 20
        def tokenizer(self, text, **kwargs): return {"input_ids": [1, 2]}
        def encode(self, *args, **kwargs): raise TimeoutError("encode offline")
    model = Model()
    embedder = SentenceTransformerEmbedder(model=model)
    for call in [lambda: embedder.embed_query("offset"),
                 lambda: embedder.embed_documents(["offset"])]:
        with pytest.raises(RetrievalOperationalError) as error:
            call()
        assert isinstance(error.value.__cause__, TimeoutError)
    model.encode = lambda *args, **kwargs: [float("nan"), 0]
    with pytest.raises(ValueError, match="NaN"):
        embedder.embed_query("offset")


def test_chroma_initialization_io_failure_is_classified(monkeypatch, tmp_path):
    chromadb = pytest.importorskip("chromadb")
    def unavailable(*args, **kwargs): raise OSError("database offline")
    monkeypatch.setattr(chromadb, "PersistentClient", unavailable)
    with pytest.raises(RetrievalOperationalError) as error:
        ChromaIndex(tmp_path / "chroma")
    assert error.value.operation == "Chroma 初始化"
    assert isinstance(error.value.__cause__, OSError)


def test_constructor_defers_known_read_failure_but_reports_it_in_request():
    sources, keyword, vector, _ = setup()
    vector.read_fault = RetrievalOperationalError("storage offline")
    retriever = TwoBranchRetriever(sources, keyword_index=keyword, vector_index=vector)
    result = retriever.search("offset", allow_degraded=True)
    assert result.status == "degraded"
    assert result.branches["vector"].failure_stage == "validation_read"


def test_candidate_cli_handles_model_initialization_failure(tmp_path, monkeypatch, capsys):
    from examples import day09_candidates
    class UnavailableEmbedder:
        def __init__(self):
            with operational_boundary("受控模型加载"):
                raise OSError("offline")
    monkeypatch.setattr(day09_candidates, "SmokeEmbedder", UnavailableEmbedder)
    monkeypatch.setattr("sys.argv", ["demo", "--smoke", "--fuse", "--allow-degraded",
                                    "--query-id", "cli-001", "--output-root", str(tmp_path)])
    day09_candidates.main()
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["query_id"] == "cli-001"
    assert result["status"] == "degraded"
    assert result["branches"]["vector"]["failure_stage"] == "initialization"
    assert [source["source_id"] for source in result["final_sources"]] == ["doc-offset"]


def test_chroma_search_and_read_errors_are_adapted_but_dimension_errors_are_not(tmp_path, monkeypatch):
    pytest.importorskip("chromadb")
    from chromadb.errors import InvalidDimensionException, RateLimitError

    class Embedder:
        def embed_documents(self, texts): return [[1, 0] for _ in texts]
        def embed_query(self, query): return [1, 0]

    sources, keyword, _, _ = setup()
    vector = ChromaIndex(tmp_path / "chroma", embedder=Embedder())
    vector.add(sources)
    retriever = TwoBranchRetriever(sources, keyword_index=keyword, vector_index=vector)
    def limit(*args, **kwargs): raise RateLimitError("busy")
    monkeypatch.setattr(type(vector.collection), "query", limit)
    result = retriever.search("offset", allow_degraded=True)
    assert result.status == "degraded"
    assert result.branches["vector"].error_type == "RateLimitError"
    assert result.branches["vector"].error_operation == "Chroma query"
    def invalid(*args, **kwargs): raise InvalidDimensionException("bad dimension")
    monkeypatch.setattr(type(vector.collection), "query", invalid)
    with pytest.raises(InvalidDimensionException):
        retriever.search("offset", allow_degraded=True)
    def offline(*args, **kwargs): raise OSError("read offline")
    monkeypatch.setattr(type(vector.collection), "get", offline)
    result = retriever.search("offset", allow_degraded=True)
    assert result.branches["vector"].failure_stage == "validation_read"
    assert result.branches["vector"].error_type == "OSError"


def test_failure_demo_saves_separate_statistics(tmp_path, monkeypatch):
    from examples.day09_failures import main
    monkeypatch.setattr("sys.argv", ["demo", "--output-root", str(tmp_path)])
    main()
    payload = json.loads(next(tmp_path.glob("*/failures.json")).read_text(encoding="utf-8"))
    assert payload["status_counts"] == {"ok": 2, "empty": 1, "failed": 2, "degraded": 4}
    assert set(payload["full_dual_branch_query_ids"]).isdisjoint(payload["degraded_query_ids"])
    for record in payload["records"]:
        if record["result"]["status"] == "failed":
            assert record["context"] is None


@pytest.mark.parametrize("status", ["failed", "degraded"])
def test_replay_rejects_degraded_candidates_for_fair_comparison(tmp_path, status):
    from examples.day09_fusion import load_saved_candidates
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps({"result": {"status": status, "branches": {}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="完整双路"):
        load_saved_candidates(path, tmp_path)
