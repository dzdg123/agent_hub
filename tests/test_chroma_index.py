from pathlib import Path

import pytest

pytest.importorskip("chromadb", reason="Chroma 存储测试需要 pip install -e '.[vector]'")

from research_agent.models import Source
from research_agent.retrieval import ChromaIndex, IndexConfigurationError, IndexDataError


class FakeEmbedder:
    def __init__(self) -> None:
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(texts)
        mapping = {
            "Agent 使用模型和工具完成任务。": [1.0, 0.0],
            "番茄炒蛋是一道菜。": [0.0, 1.0],
        }
        return [mapping[text] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return [1.0, 0.0]


def make_sources() -> list[Source]:
    return [
        Source(
            source_id="smoke-agent",
            title="Agent 笔记",
            content="Agent 使用模型和工具完成任务。",
            file_path="agent.md",
            metadata={"topic": "agent", "tags": ["model", "tool"]},
        ),
        Source(
            source_id="smoke-food",
            title="菜谱",
            content="番茄炒蛋是一道菜。",
            page=2,
            metadata={"topic": "food"},
        ),
    ]


def make_index(path: Path, embedder: FakeEmbedder) -> ChromaIndex:
    return ChromaIndex(
        embedder=embedder,
        path=path,
        collection_name="test-explicit-cosine-v1",
    )


def test_empty_add_does_not_call_embedder(tmp_path: Path):
    embedder = FakeEmbedder()
    index = make_index(tmp_path / "chroma", embedder)

    index.add([])

    assert embedder.document_calls == []
    assert index.all() == []


def test_add_and_search_encode_exactly_once(tmp_path: Path):
    embedder = FakeEmbedder()
    index = make_index(tmp_path / "chroma", embedder)
    sources = make_sources()

    index.add(sources)
    results = index.search("什么是 Agent？", top_k=2)

    assert embedder.document_calls == [[source.content for source in sources]]
    assert embedder.query_calls == ["什么是 Agent？"]
    assert [source.source_id for source in results] == [
        "smoke-agent",
        "smoke-food",
    ]
    assert results[0].score == pytest.approx(1.0)
    assert results[1].score == pytest.approx(0.0)


def test_source_metadata_round_trip(tmp_path: Path):
    embedder = FakeEmbedder()
    index = make_index(tmp_path / "chroma", embedder)
    original = make_sources()[0]
    original = original.model_copy(update={
        "url": "https://example.test/notes",
        "page": 3,
        "metadata": {
            "relative_path": "notes.pdf", "file_type": "pdf",
            "offset": 12, "end_offset": 28, "offset_basis": "normalized_page_text",
            "empty_pages": [2], "warnings": ["第 2 页未提取到文本"],
            "nested": {"tags": ["原始来源", "工具"]},
        },
    })

    index.add([original])
    restored = index.get(original.source_id)

    assert restored is not None
    assert restored.source_id == original.source_id
    assert restored.title == original.title
    assert restored.content == original.content
    assert restored.file_path == original.file_path
    assert restored.metadata == original.metadata
    assert restored.fetched_at == original.fetched_at
    assert restored.model_dump() == original.model_dump()


def test_persistence_delete_and_all(tmp_path: Path):
    path = tmp_path / "chroma"
    first_embedder = FakeEmbedder()
    first = make_index(path, first_embedder)
    first.add(make_sources())

    reopened = make_index(path, FakeEmbedder())
    assert [source.source_id for source in reopened.all()] == [
        "smoke-agent",
        "smoke-food",
    ]

    reopened.delete(["smoke-food"])
    assert reopened.get("smoke-food") is None
    assert [source.source_id for source in reopened.all()] == ["smoke-agent"]


@pytest.mark.parametrize("top_k", [0, -1, 1.5, True])
def test_search_rejects_invalid_top_k(tmp_path: Path, top_k):
    index = make_index(tmp_path / "chroma", FakeEmbedder())

    with pytest.raises(ValueError, match="top_k 必须是正整数"):
        index.search("问题", top_k=top_k)


def test_old_path_constructor_is_lazy_and_empty_operations_are_noops(tmp_path: Path):
    index = ChromaIndex(tmp_path / "chroma")
    assert index.embedder is None
    index.add([])
    index.delete([])
    assert index.search("问题") == []
    assert index.search(" \n\t") == []
    assert index.count() == 0
    assert index.embedder is None


def test_duplicate_batch_rejected_before_encoding(tmp_path: Path):
    embedder = FakeEmbedder()
    index = make_index(tmp_path / "chroma", embedder)
    source = make_sources()[0]
    with pytest.raises(ValueError, match="重复"):
        index.add([source, source])
    assert embedder.document_calls == []
    assert index.count() == 0


def test_upsert_updates_existing_record_without_growing_count(tmp_path: Path):
    index = make_index(tmp_path / "chroma", FakeEmbedder())
    original = make_sources()[0]
    index.add([original])
    updated = original.model_copy(update={"content": make_sources()[1].content})
    index.add([updated])
    assert index.count() == 1
    assert index.get(original.source_id).content == updated.content
    index.delete([original.source_id])
    assert index.count() == 0


def test_query_keeps_distance_and_does_not_mutate_stored_metadata(tmp_path: Path):
    embedder = FakeEmbedder()
    index = make_index(tmp_path / "chroma", embedder)
    original = make_sources()[0]
    original.metadata.update({"offset": 10, "warnings": ["空白页"], "nested": {"a": 1}})
    index.add([original])
    assert index.search(" ") == []
    assert embedder.query_calls == []
    result = index.search("问题", top_k=99)[0]
    assert result.metadata["_retrieval"] == {"metric": "cosine", "distance": 0.0}
    assert result.fetched_at == original.fetched_at
    assert index.get(original.source_id).metadata == original.metadata


@pytest.mark.parametrize("vectors", [[], [[]], [[0.0, 0.0]], [[float("nan"), 1]], [[float("inf"), 1]], [[True, 1]]])
def test_bad_model_output_is_rejected_before_write(tmp_path: Path, vectors):
    embedder = FakeEmbedder()
    embedder.embed_documents = lambda texts: vectors
    index = make_index(tmp_path / "chroma", embedder)
    with pytest.raises(IndexDataError):
        index.add([make_sources()[0]])
    assert index.count() == 0


def test_mixed_dimensions_are_rejected_before_write(tmp_path: Path):
    embedder = FakeEmbedder()
    embedder.embed_documents = lambda texts: [[1.0, 0.0], [1.0, 0.0, 0.0]]
    index = make_index(tmp_path / "chroma", embedder)
    with pytest.raises(IndexConfigurationError, match="维度"):
        index.add(make_sources())
    assert index.count() == 0


def test_reopened_index_validates_stored_dimension_for_query_and_add(tmp_path: Path):
    path = tmp_path / "chroma"
    first = make_index(path, FakeEmbedder())
    first.add(make_sources())
    embedder = FakeEmbedder()
    embedder.embed_query = lambda text: [1.0, 0.0, 0.0]
    embedder.embed_documents = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]
    reopened = make_index(path, embedder)
    with pytest.raises(IndexConfigurationError, match="维度"):
        reopened.search("问题")
    with pytest.raises(IndexConfigurationError, match="维度"):
        reopened.add(make_sources())
    assert reopened.count() == 2


@pytest.mark.parametrize("damage", ["json", "missing", "time", "page"])
def test_corrupt_record_raises_instead_of_returning_empty(tmp_path: Path, damage):
    index = make_index(tmp_path / "chroma", FakeEmbedder())
    source = make_sources()[0]
    metadata = index._source_to_metadata(source)
    if damage == "json":
        metadata["source_metadata_json"] = "{broken"
    elif damage == "missing":
        del metadata["fetched_at"]
    elif damage == "time":
        metadata["fetched_at"] = "invalid"
    else:
        metadata["page"] = -1
    index.collection.upsert(
        ids=[source.source_id], documents=[source.content],
        embeddings=[[1.0, 0.0]], metadatas=[metadata],
    )
    with pytest.raises(IndexDataError):
        index.get(source.source_id)
    with pytest.raises(IndexDataError):
        index.search("问题")


def test_wrong_distance_configuration_rejected(tmp_path: Path):
    import chromadb

    path = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(path))
    client.create_collection(
        "test-explicit-cosine-v1", embedding_function=None,
        configuration={"hnsw": {"space": "l2"}},
    )
    with pytest.raises(IndexConfigurationError):
        make_index(path, FakeEmbedder())


def test_storage_failure_is_not_hidden(tmp_path: Path, monkeypatch):
    index = make_index(tmp_path / "chroma", FakeEmbedder())
    index.add(make_sources())

    def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(type(index.collection), "query", fail)
    with pytest.raises(RuntimeError, match="database unavailable"):
        index.search("问题")
