from pathlib import Path

from research_agent.documents import load_all_documents_detailed
from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.vector_math import cosine


print(cosine([1, 0], [1, 0]))
print(cosine([1, 0], [0, 1]))
print(cosine([3, 1], [1, 3]))
print(cosine([1, 0], [10, 0]))

embedder = SentenceTransformerEmbedder(model_name="BAAI/bge-small-zh-v1.5", device="cpu")

texts = [
    "汽车需要定期保养。",
    "今天的天气很好。",
]

document_vectors = embedder.embed_documents(texts)

query_vector = embedder.embed_query("如何保养汽车")

print(len(document_vectors))
print(len(document_vectors[0]))
print(len(query_vector))
for document_vector in document_vectors:
    print(cosine(document_vector, query_vector))


def token_length(model, text: str) -> int:
    encoded = model.tokenizer(
        text,
        truncation=False,
        add_special_tokens=True,
    )
    return len(encoded["input_ids"])


def audit_sources(model, sources) -> None:
    limit = model.max_seq_length
    rows = []

    for source in sources:
        length = token_length(model, source.content)
        rows.append((length, source.source_id))

    over_limit = [
        (length, source_id)
        for length, source_id in rows
        if length > limit
    ]

    print("source_count:", len(rows))
    print("model_limit:", limit)
    print("max_token_length:", max((length for length, _ in rows), default=0))
    print("over_limit_count:", len(over_limit))

    for length, source_id in sorted(over_limit, reverse=True):
        print("OVER_LIMIT:", source_id, length)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_ROOT = PROJECT_ROOT / "data" / "day07" / "input"

# 必须从原始文档重新生成 Source；不要二次切割旧 Source.content。
load_result = load_all_documents_detailed(
    DOCUMENT_ROOT,
    chunk_size=400,
    overlap=60,
)
sources = load_result.sources

print("document_root:", DOCUMENT_ROOT)
print("loaded_files:", load_result.loaded_files)
print("failed_files:", load_result.failed_files)
print("source_count:", len(sources))

for error in load_result.errors:
    print("LOAD_ERROR:", error.relative_path, error.error_code, error.message)

audit_sources(embedder.model, sources)

question = "如何保养汽车"
query_input = f"{embedder.query_instruction or ''}{question}"
print("query_token_length:", token_length(embedder.model, query_input))
print("model_limit:", embedder.model.max_seq_length)
