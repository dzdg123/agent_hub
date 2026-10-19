from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .embeddings import Embedder
from .models import Source


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9_]+", lowered)
    chinese = [lowered[i : i + 2] for i in range(len(lowered) - 1) if "\u4e00" <= lowered[i] <= "\u9fff"]
    return latin + chinese


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


class HybridIndex:
    """A deterministic educational index combining token and character similarity."""

    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}

    def add(self, sources: list[Source]) -> None:
        for source in sources:
            self._sources[source.source_id] = source

    def delete(self, source_ids: list[str]) -> None:
        for source_id in source_ids:
            self._sources.pop(source_id, None)

    def all(self) -> list[Source]:
        return list(self._sources.values())

    def get(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    def search(self, query: str, top_k: int = 5) -> list[Source]:
        query_tokens = Counter(tokenize(query))
        query_chars = Counter(query.lower())
        scored: list[tuple[float, Source]] = []
        for source in self._sources.values():
            keyword_score = _cosine(query_tokens, Counter(tokenize(source.content)))
            char_score = _cosine(query_chars, Counter(source.content.lower()))
            score = 0.7 * keyword_score + 0.3 * char_score
            if score > 0:
                scored.append((score, source.model_copy(update={"score": score})))
        scored.sort(key=lambda pair: (-pair[0], pair[1].source_id))
        return [source for _, source in scored[:top_k]]


def merge_ranked(result_sets: list[list[Source]], top_k: int = 10) -> list[Source]:
    """Merge result lists with reciprocal rank fusion and source-id deduplication."""
    scores: dict[str, float] = {}
    sources: dict[str, Source] = {}
    for results in result_sets:
        for rank, source in enumerate(results, 1):
            scores[source.source_id] = scores.get(source.source_id, 0.0) + 1.0 / (60 + rank)
            sources[source.source_id] = source
    ordered = sorted(scores, key=lambda source_id: (-scores[source_id], source_id))
    return [sources[source_id].model_copy(update={"score": scores[source_id]}) for source_id in ordered[:top_k]]


class IndexDataError(RuntimeError):
    """模型输出或持久化记录不符合索引契约。"""


class IndexConfigurationError(RuntimeError):
    """模型向量或集合配置不匹配。"""


class ChromaIndex:
    """Persistent cosine index using embeddings produced by the application."""

    def __init__(
        self,
        path: str | Path = "data/chroma",
        *,
        collection_name: str = "research-cosine-source-v2",
        embedder: Embedder | None = None,
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("请安装 pip install -e '.[vector]' 后使用 ChromaIndex") from exc

        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )

        configuration = self.collection.configuration
        distance = (configuration.get("hnsw") or {}).get("space")
        if distance != "cosine":
            raise IndexConfigurationError(
                f"集合 {collection_name!r} 已存在，但距离配置是 {distance!r}，不是 'cosine'；"
                "请使用新的集合名"
            )

    def _get_embedder(self) -> Embedder:
        if self.embedder is None:
            from .embeddings import SentenceTransformerEmbedder

            self.embedder = SentenceTransformerEmbedder()
        return self.embedder

    def count(self) -> int:
        return self.collection.count()

    def _stored_dimension(self) -> int | None:
        result = self.collection.get(limit=1, include=["embeddings"])
        vectors = result.get("embeddings")
        if vectors is None or len(vectors) == 0:
            return None
        return len(vectors[0])

    def _validate_vectors(self, vectors: Any, expected_count: int) -> list[list[float]]:
        if not isinstance(vectors, (list, tuple)) or len(vectors) != expected_count:
            raise IndexDataError(f"向量数量必须等于输入数量 {expected_count}")
        dimension = self._stored_dimension()
        validated = []
        for row in vectors:
            if not isinstance(row, (list, tuple)) or not row:
                raise IndexDataError("模型必须输出非空的一维数值向量")
            if any(isinstance(value, (bool, str, bytes)) for value in row):
                raise IndexDataError("向量分量必须是数值")
            try:
                vector = [float(value) for value in row]
            except (TypeError, ValueError, OverflowError) as exc:
                raise IndexDataError("向量分量必须是有限数值") from exc
            if not all(math.isfinite(value) for value in vector):
                raise IndexDataError("向量包含 NaN 或无穷大")
            if not any(value != 0.0 for value in vector):
                raise IndexDataError("cosine 索引不接受零向量")
            if dimension is None:
                dimension = len(vector)
            if len(vector) != dimension:
                raise IndexConfigurationError(
                    f"向量维度不一致：期望 {dimension}，实际 {len(vector)}"
                )
            validated.append(vector)
        return validated

    def add(self, sources: list[Source]) -> None:
        if not sources:
            return

        ids = [source.source_id for source in sources]
        if any(not source_id.strip() for source_id in ids):
            raise ValueError("source_id 不能为空")
        if len(ids) != len(set(ids)):
            raise ValueError("本批次包含重复 source_id")
        if any(not source.content.strip() for source in sources):
            raise ValueError("Source.content 不能为空")
        metadatas = [self._source_to_metadata(source) for source in sources]
        documents = [source.content for source in sources]
        embeddings = self._validate_vectors(
            self._get_embedder().embed_documents(documents), len(sources)
        )

        self.collection.upsert(
            ids=[source.source_id for source in sources],
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def delete(self, source_ids: list[str]) -> None:
        if source_ids:
            self.collection.delete(ids=list(dict.fromkeys(source_ids)))

    def all(self) -> list[Source]:
        result = self.collection.get(include=["documents", "metadatas"])
        sources = self._sources_from_get(result)
        return sorted(sources, key=lambda source: source.source_id)

    def get(self, source_id: str) -> Source | None:
        result = self.collection.get(
            ids=[source_id],
            include=["documents", "metadatas"],
        )
        sources = self._sources_from_get(result)
        return sources[0] if sources else None

    def search(self, query: str, top_k: int = 5) -> list[Source]:
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
            raise ValueError("top_k 必须是正整数")
        if not isinstance(query, str):
            raise TypeError("query 必须是字符串")
        if not query.strip():
            return []

        count = self.count()
        if count == 0:
            return []

        query_embedding = self._validate_vectors(
            [self._get_embedder().embed_query(query)], 1
        )[0]
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )

        rows = self._aligned_columns(result, query=True)
        ids, documents, metadatas, distances = rows

        sources: list[Source] = []
        for source_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=True,
        ):
            if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance):
                raise IndexDataError("查询返回了非法 distance")
            source = self._source_from_record(
                source_id=source_id,
                document=document,
                metadata=metadata,
                score=1.0 - float(distance),
            )
            source.metadata["_retrieval"] = {
                "metric": "cosine", "distance": float(distance),
            }
            sources.append(source)
        return sources

    @staticmethod
    def _source_to_metadata(source: Source) -> dict[str, Any]:
        if source.page is not None and source.page <= 0:
            raise ValueError("Source.page 必须是正整数或 None")
        if "_retrieval" in source.metadata:
            raise ValueError("Source.metadata 的 _retrieval 是保留检索字段")
        try:
            metadata_json = json.dumps(
                source.metadata, ensure_ascii=False, sort_keys=True, allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise IndexDataError(f"Source {source.source_id!r} 的 metadata 无法序列化") from exc
        return {
            "title": source.title,
            "url": source.url or "",
            "file_path": source.file_path or "",
            "page": source.page or 0,
            "source_schema_version": 1,
            "source_metadata_json": metadata_json,
            "fetched_at": source.fetched_at.isoformat(),
        }

    @classmethod
    def _source_from_record(
        cls,
        *,
        source_id: str,
        document: str,
        metadata: dict[str, Any],
        score: float = 0.0,
    ) -> Source:
        try:
            required = ("title", "url", "file_path", "source_metadata_json", "fetched_at")
            if not isinstance(metadata, dict) or any(
                not isinstance(metadata[key], str) for key in required
            ):
                raise ValueError("来源字段缺失或类型错误")
            if type(metadata["source_schema_version"]) is not int or metadata["source_schema_version"] != 1:
                raise ValueError("不支持的来源格式版本")
            if type(metadata["page"]) is not int or metadata["page"] < 0:
                raise ValueError("page 必须是非负整数")
            if not isinstance(document, str) or not isinstance(source_id, str):
                raise ValueError("正文或 ID 缺失")
            source_metadata = json.loads(metadata["source_metadata_json"])
            if not isinstance(source_metadata, dict) or "_retrieval" in source_metadata:
                raise ValueError("来源 metadata 必须是字典且不能包含保留字段")
            fetched_at = datetime.fromisoformat(metadata["fetched_at"])
            return Source(
                source_id=source_id,
                content=document,
                title=metadata["title"],
                url=metadata["url"] or None,
                file_path=metadata["file_path"] or None,
                page=metadata["page"] or None,
                fetched_at=fetched_at,
                metadata=source_metadata,
                score=score,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IndexDataError(f"Source {source_id!r} 的索引数据损坏或格式不兼容") from exc

    @staticmethod
    def _aligned_columns(result: dict[str, Any], *, query: bool = False) -> list[list]:
        fields = ["ids", "documents", "metadatas"]
        if query:
            fields.append("distances")
        columns = []
        for field in fields:
            column = result.get(field)
            if not isinstance(column, list):
                raise IndexDataError(f"Chroma 返回字段 {field!r} 缺失或格式错误")
            if query:
                if len(column) != 1 or not isinstance(column[0], list):
                    raise IndexDataError(f"Chroma 返回字段 {field!r} 查询分组错误")
                column = column[0]
            columns.append(column)
        if len({len(column) for column in columns}) != 1:
            raise IndexDataError("Chroma 返回数组长度不一致")
        return columns

    @classmethod
    def _sources_from_get(cls, result: dict[str, Any]) -> list[Source]:
        ids, documents, metadatas = cls._aligned_columns(result)
        return [
            cls._source_from_record(
                source_id=source_id,
                document=document,
                metadata=metadata,
            )
            for source_id, document, metadata in zip(
                ids,
                documents,
                metadatas,
                strict=True,
            )
        ]

