from pathlib import Path

import chromadb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHROMA_PATH = PROJECT_ROOT / "data" / "day08" / "chroma-smoke"


def main() -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_or_create_collection(
        name="day08-smoke-cosine-v1",
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
    )
    collection.upsert(
        ids=["smoke-agent", "smoke-food"],
        documents=["Agent 使用模型和工具完成任务。", "番茄炒蛋是一道菜。"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[{"topic": "agent"}, {"topic": "food"}],
    )

    result = collection.query(
        query_embeddings=[[1.0, 0.0]],
        n_results=2,
        include=["documents", "metadatas", "distances"],
    )
    print("configuration:", collection.configuration)

    for source_id, document, metadata, distance in zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
        strict=True,
    ):
        print(
            {
                "id": source_id,
                "document": document,
                "metadata": metadata,
                "distance": distance,
            }
        )


if __name__ == "__main__":
    main()
