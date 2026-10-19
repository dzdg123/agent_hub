from pathlib import Path
import json
from datetime import datetime, timezone

from research_agent.documents import load_all_documents_detailed
from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.retrieval import ChromaIndex


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_ROOT = PROJECT_ROOT / "data" / "day07" / "input"
CHROMA_PATH = PROJECT_ROOT / "data" / "day08" / "chroma-bge-c400"
COLLECTION_NAME = "day08-bge-small-zh-v15-cosine-c400-o60-v2"


def main() -> None:
    load_result = load_all_documents_detailed(
        DOCUMENT_ROOT,
        chunk_size=400,
        overlap=60,
    )
    for error in load_result.errors:
        print("LOAD_ERROR:", error.relative_path, error.error_code, error.message)

    embedder = SentenceTransformerEmbedder(
        model_name="BAAI/bge-small-zh-v1.5",
        device="cpu",
        query_instruction=None,
    )
    index = ChromaIndex(
        embedder=embedder,
        path=CHROMA_PATH,
        collection_name=COLLECTION_NAME,
    )
    try:
        index.add(load_result.sources)
    except Exception as exc:
        # 记录失败批次并继续抛出；不假定数据库具有应用级批次事务保证。
        failure_path = CHROMA_PATH.parent / "last-index-failure.json"
        failure_path.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "collection": COLLECTION_NAME,
                    "source_ids": [source.source_id for source in load_result.sources],
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        raise

    query = "Agent 如何使用模型和工具完成任务？"
    results = index.search(query, top_k=3)

    print("indexed_sources:", index.count())
    print("query:", query)
    for rank, source in enumerate(results, start=1):
        print(
            {
                "rank": rank,
                "source_id": source.source_id,
                "title": source.title,
                "score": source.score,
                "content": source.content,
            }
        )


if __name__ == "__main__":
    main()
