import sys
from types import ModuleType

import pytest

from research_agent.embeddings import SentenceTransformerEmbedder


class FakeTokenizer:
    def __call__(
        self,
        text: str,
        *,
        truncation: bool,
        add_special_tokens: bool,
    ) -> dict[str, list[int]]:
        assert truncation is False
        extra = 2 if add_special_tokens else 0
        return {"input_ids": list(range(len(text) + extra))}


class FakeModel:
    max_seq_length = 6

    def __init__(self) -> None:
        self.tokenizer = FakeTokenizer()
        self.calls: list[tuple[object, dict[str, object]]] = []

    def encode(self, value, **kwargs):
        self.calls.append((value, kwargs))
        if isinstance(value, list):
            return [[1, 0] for _ in value]
        return [1, 0]


def test_empty_document_list_does_not_call_model():
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(model=model)

    assert embedder.embed_documents([]) == []
    assert model.calls == []


def test_documents_are_normalized_and_converted_to_float():
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(model=model)

    vectors = embedder.embed_documents(["短文"])

    assert vectors == [[1.0, 0.0]]
    assert model.calls[0][1]["normalize_embeddings"] is True


def test_overlong_document_is_rejected_before_encoding():
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(model=model)

    with pytest.raises(ValueError, match="超过模型长度限制"):
        embedder.embed_documents(["12345"])

    assert model.calls == []


def test_query_instruction_counts_toward_length_limit():
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(
        model=model,
        query_instruction="指令",
    )

    with pytest.raises(ValueError, match="实际 7 tokens，限制 6 tokens"):
        embedder.embed_query("问题一")

    assert model.calls == []


@pytest.mark.parametrize("text", ["", " ", "\n\t"])
def test_v10_blank_text_and_query_fail_before_model_encoding(text):
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(model=model)
    with pytest.raises(ValueError, match="不能为空"):
        embedder.embed_documents(["合法", text])
    with pytest.raises(ValueError, match="不能为空"):
        embedder.embed_query(text)
    assert model.calls == []


def test_v12_exact_limit_accepted_but_overlong_query_and_batch_rejected():
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(model=model)
    assert embedder.embed_query("1234") == [1.0, 0.0]  # 4 + 2 special tokens = 6
    model.calls.clear()
    with pytest.raises(ValueError, match="实际 7 tokens"):
        embedder.embed_query("12345")
    with pytest.raises(ValueError, match="texts\\[1\\]"):
        embedder.embed_documents(["合法", "12345"])
    assert model.calls == []


def test_one_loaded_model_reused_with_distinct_document_and_query_preprocessing():
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(model=model, query_instruction="查:")
    embedder.embed_documents(["正文"])
    embedder.embed_query("问题")
    embedder.embed_query("新问")
    assert embedder.model is model
    assert [value for value, _ in model.calls] == [["正文"], "查:问题", "查:新问"]
    assert all(kwargs["normalize_embeddings"] is True for _, kwargs in model.calls)


@pytest.mark.parametrize("output", [[], [float("nan"), 0], [float("inf"), 0], [[1, 0]]])
def test_v09_v10_bad_query_model_output_is_not_returned(output):
    model = FakeModel()
    model.encode = lambda *args, **kwargs: output
    embedder = SentenceTransformerEmbedder(model=model)
    with pytest.raises(ValueError):
        embedder.embed_query("问题")


def test_v09_document_output_count_and_query_dimension_mismatch():
    model = FakeModel()
    embedder = SentenceTransformerEmbedder(model=model)
    model.encode = lambda *args, **kwargs: [[1, 0]]
    with pytest.raises(ValueError, match="返回 1 个向量"):
        embedder.embed_documents(["甲", "乙"])
    embedder.embed_documents(["甲"])
    model.encode = lambda *args, **kwargs: [1, 0, 0]
    with pytest.raises(ValueError, match="维度不一致"):
        embedder.embed_query("问题")


def test_model_load_failure_retains_underlying_cause(monkeypatch):
    module = ModuleType("sentence_transformers")
    cause = OSError("simulated offline model unavailable")

    def unavailable(*args, **kwargs):
        raise cause

    module.SentenceTransformer = unavailable
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    with pytest.raises(RuntimeError, match="未就绪") as error:
        SentenceTransformerEmbedder()
    assert error.value.__cause__ is cause
