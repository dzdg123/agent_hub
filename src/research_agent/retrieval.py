from __future__ import annotations

import math
import re
from collections import Counter

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


class ChromaIndex:
    """Optional production-like vector index, loaded only when extras are installed."""

    def __init__(self, path: str = "data/chroma") -> None:
        try:
            import chromadb
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        except ImportError as exc:
            raise RuntimeError("请安装 pip install -e '.[vector]' 后使用 ChromaIndex") from exc
        client = chromadb.PersistentClient(path=path)
        embedding = SentenceTransformerEmbeddingFunction(model_name="BAAI/bge-small-zh-v1.5")
        self.collection = client.get_or_create_collection("research", embedding_function=embedding)

    def add(self, sources: list[Source]) -> None:
        if not sources:
            return
        self.collection.upsert(
            ids=[source.source_id for source in sources],
            documents=[source.content for source in sources],
            metadatas=[
                {
                    "title": source.title,
                    "url": source.url or "",
                    "file_path": source.file_path or "",
                    "page": source.page or 0,
                }
                for source in sources
            ],
        )

