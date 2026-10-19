from __future__ import annotations

import math
from typing import Any, Protocol, Sequence


class Embedder(Protocol):
    """Common interface used by retrieval code to create text vectors."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    """Encode documents and queries with one shared SentenceTransformer model."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        *,
        device: str = "cpu",
        revision: str | None = None,
        query_instruction: str | None = None,
        model: Any | None = None,
    ) -> None:
        if model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "请安装 pip install -e '.[vector]' 后使用 SentenceTransformerEmbedder"
                ) from exc

            model_kwargs: dict[str, object] = {"device": device}
            if revision is not None:
                model_kwargs["revision"] = revision
            try:
                model = SentenceTransformer(model_name, **model_kwargs)
            except Exception as exc:
                raise RuntimeError(f"Embedding 模型 {model_name!r} 未就绪：加载或下载失败") from exc

        self.model = model
        self.model_name = model_name
        self.device = device
        self.revision = revision
        self.query_instruction = query_instruction
        self._dimension: int | None = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        for index, text in enumerate(texts):
            self._validate_text(text, name=f"texts[{index}]")
            self._validate_model_length(text, name=f"texts[{index}]")

        encoded = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        rows = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        if len(rows) != len(texts):
            raise ValueError(
                f"模型返回 {len(rows)} 个向量，但输入包含 {len(texts)} 个文档"
            )
        return [self._to_float_vector(row) for row in rows]

    def embed_query(self, text: str) -> list[float]:
        self._validate_text(text, name="text")
        query = f"{self.query_instruction}{text}" if self.query_instruction else text
        self._validate_model_length(query, name="query")
        encoded = self.model.encode(
            query,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        values = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        return self._to_float_vector(values)

    @staticmethod
    def _validate_text(text: str, *, name: str) -> None:
        if not isinstance(text, str):
            raise TypeError(f"{name} 必须是字符串")
        if not text.strip():
            raise ValueError(f"{name} 不能为空")

    def token_length(self, text: str) -> int:
        """Return the tokenizer length, including model special tokens."""
        self._validate_text(text, name="text")
        encoded = self.model.tokenizer(
            text,
            truncation=False,
            add_special_tokens=True,
        )
        return len(encoded["input_ids"])

    def _validate_model_length(self, text: str, *, name: str) -> None:
        actual = self.token_length(text)
        limit = int(self.model.max_seq_length)
        if actual > limit:
            raise ValueError(
                f"{name} 超过模型长度限制：实际 {actual} tokens，限制 {limit} tokens"
            )

    def _to_float_vector(self, values: Sequence[float]) -> list[float]:
        try:
            vector = [float(value) for value in values]
        except (TypeError, ValueError) as exc:
            raise ValueError("模型输出必须是一维数值向量") from exc

        if not vector:
            raise ValueError("模型输出了空向量")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("模型输出包含 NaN 或无穷大")

        dimension = len(vector)
        if self._dimension is None:
            self._dimension = dimension
        elif dimension != self._dimension:
            raise ValueError(
                f"向量维度不一致：期望 {self._dimension}，实际 {dimension}"
            )
        return vector
