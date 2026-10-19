"""阶段九的缺项行为测试；已有契约继续由 test_chroma_index.py 覆盖。"""

from pathlib import Path

import pytest

pytest.importorskip("chromadb", reason="V01～V12 存储集成测试需要安装 .[vector]")

from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.models import Source
from research_agent.retrieval import ChromaIndex, IndexDataError


class ControlledEmbedder:
    def __init__(self):
        self.document_calls = []
        self.query_calls = []

    def embed_documents(self, texts):
        self.document_calls.append(list(texts))
        mapping = {"正向文档": [1.0, 0.0], "正交文档": [0.0, 1.0], "反向文档": [-1.0, 0.0]}
        return [mapping[text] for text in texts]

    def embed_query(self, text):
        self.query_calls.append(text)
        return [1.0, 0.0]


@pytest.fixture
def stored_index(tmp_path):
    embedder = ControlledEmbedder()
    index = ChromaIndex(tmp_path / "chroma", embedder=embedder)
    index.add([
        Source(source_id="doc-1", title="正向", content="正向文档"),
        Source(source_id="doc-10", title="正交", content="正交文档"),
        Source(source_id="doc-100", title="反向", content="反向文档"),
    ])
    return index, embedder


def test_v03_v04_cosine_order_negative_score_and_top_k_cap(stored_index, monkeypatch):
    index, embedder = stored_index
    captured = []
    original = type(index.collection).query

    def capture(collection, *args, **kwargs):
        captured.append(kwargs)
        return original(collection, *args, **kwargs)

    monkeypatch.setattr(type(index.collection), "query", capture)
    results = index.search("受控查询", top_k=99)
    assert len(results) == 3
    assert [source.source_id for source in results] == ["doc-1", "doc-10", "doc-100"]
    assert [source.metadata["_retrieval"]["distance"] for source in results] == pytest.approx([0, 1, 2])
    assert [source.score for source in results] == pytest.approx([1, 0, -1])
    assert captured[0]["n_results"] == 3
    assert captured[0]["query_embeddings"] == [[1.0, 0.0]]
    assert "query_texts" not in captured[0]
    assert len(embedder.query_calls) == 1


@pytest.mark.parametrize("top_k", [False, None, "3", float("nan")])
def test_v05_invalid_top_k_fails_even_for_empty_query(stored_index, top_k):
    index, embedder = stored_index
    with pytest.raises(ValueError, match="top_k"):
        index.search("", top_k=top_k)
    assert embedder.query_calls == []


def test_v07_v08_delete_exact_id_then_reopen_without_add(stored_index):
    index, _ = stored_index
    index.delete(["doc-1"])
    assert index.count() == 2
    assert index.collection.get(ids=["doc-1"])["ids"] == []
    assert index.get("doc-10") is not None  # 不能按 ID 前缀误删
    index.delete([])
    assert index.count() == 2
    before = [source.model_dump() for source in index.all()]

    reader = ControlledEmbedder()
    reopened = ChromaIndex(Path(index.client.get_settings().persist_directory), embedder=reader)
    assert reopened.count() == 2
    assert [source.model_dump() for source in reopened.all()] == before
    hits = reopened.search("再次查询", top_k=10)
    assert [source.source_id for source in hits] == ["doc-10", "doc-100"]
    assert reopened.get("doc-1") is None
    assert reader.document_calls == []


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_v10_invalid_document_batch_does_not_write_or_encode(stored_index, text):
    index, embedder = stored_index
    before = index.all()
    embedder.document_calls.clear()
    with pytest.raises(ValueError, match="content"):
        index.add([
            Source(source_id="new-valid", title="有效", content="正向文档"),
            Source(source_id="new-empty", title="空", content=text),
        ])
    assert index.all() == before
    assert embedder.document_calls == []


@pytest.mark.parametrize("vector", [[], [float("nan"), 0], [float("inf"), 0], [0, 0], [True, 0]])
def test_v10_bad_query_vectors_never_reach_storage_query(stored_index, monkeypatch, vector):
    index, embedder = stored_index
    embedder.embed_query = lambda text: vector

    def unexpected_query(*args, **kwargs):
        pytest.fail("非法向量不应到达数据库查询")

    monkeypatch.setattr(type(index.collection), "query", unexpected_query)
    with pytest.raises(IndexDataError):
        index.search("查询")


@pytest.mark.parametrize("method", ["upsert", "delete", "count"])
def test_v11_database_failures_propagate(stored_index, monkeypatch, method):
    index, _ = stored_index

    def fail(*args, **kwargs):
        raise OSError(f"storage {method} failure")

    monkeypatch.setattr(type(index.collection), method, fail)
    with pytest.raises(OSError, match=f"storage {method} failure"):
        if method == "upsert":
            index.add([Source(source_id="new", title="新", content="正向文档")])
        elif method == "delete":
            index.delete(["doc-1"])
        else:
            index.search("问题")


def test_v12_overlength_rejected_before_encode_and_index_write(tmp_path):
    class Model:
        max_seq_length = 6

        def tokenizer(self, text, **kwargs):
            assert kwargs == {"truncation": False, "add_special_tokens": True}
            return {"input_ids": list(range(len(text) + 2))}

        def encode(self, *args, **kwargs):
            pytest.fail("超长输入必须在模型编码前被拒绝")

    index = ChromaIndex(tmp_path / "chroma", embedder=SentenceTransformerEmbedder(model=Model()))
    with pytest.raises(ValueError, match="超过模型长度限制"):
        index.add([Source(source_id="long", title="长文本", content="12345")])
    assert index.count() == 0
