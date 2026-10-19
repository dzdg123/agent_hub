"""阶段六：分别启动 build 和 reopen，验证 upsert、删除及跨进程持久化。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from research_agent.models import Source
from research_agent.retrieval import ChromaIndex


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    # 使用显式异常，python -O 时也不会跳过实验检查。
    if not condition:
        raise RuntimeError(message)


def snapshot(sources: list[Source]) -> list[dict[str, Any]]:
    return [
        source.model_dump(mode="json", exclude={"score"})
        for source in sorted(sources, key=lambda source: source.source_id)
    ]


def save_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def build(args: argparse.Namespace, db_path: Path, name: str, record_path: Path) -> None:
    from research_agent.documents import load_all_documents_detailed
    from research_agent.embeddings import SentenceTransformerEmbedder

    require(not record_path.exists(), "已有实验记录；请使用新的 --version，不要覆盖删除实验。")
    index = ChromaIndex(path=db_path, collection_name=name)
    require(index.count() == 0, "集合非空；请使用新的 --version 从头实验。")

    loaded = load_all_documents_detailed(
        args.document_root.resolve(), chunk_size=400, overlap=60,
    )
    for error in loaded.errors:
        print("LOAD_ERROR:", error.relative_path, error.error_code, error.message)
    sources = loaded.sources
    ids = [source.source_id for source in sources]
    require(bool(ids), "没有可索引的 Source，请检查文档目录。")
    require(len(ids) == len(set(ids)), "语料包含重复 Source ID。")

    record: dict[str, Any] = {
        "schema_version": 1,
        "status": "building",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_path": str(db_path),
        "collection_name": name,
        "document_root": str(args.document_root.resolve()),
        "query": args.query,
        "original_count": len(sources),
        "original_ids": ids,
        "load_errors": [
            {"path": error.relative_path, "code": error.error_code, "message": error.message}
            for error in loaded.errors
        ],
        "config": {
            "model": "BAAI/bge-small-zh-v1.5",
            "revision": None,
            "normalize_embeddings": True,
            "query_instruction": None,
            "chunk_size": 400,
            "overlap": 60,
            "metric": "cosine",
        },
    }
    save_record(record_path, record)
    try:
        index.embedder = SentenceTransformerEmbedder(device="cpu")
        index.add(sources)
        record["count_after_first_add"] = index.count()
        require(index.count() == len(sources), "首次写入计数与 N 不一致。")
        save_record(record_path, record)

        index.add(sources)
        record["count_after_second_add"] = index.count()
        require(index.count() == len(sources), "重复 upsert 导致计数变化。")
        require(snapshot(index.all()) == snapshot(sources), "写入后的正文或来源信息不一致。")

        hits = index.search(args.query, top_k=3)
        require(bool(hits), "查询未命中，无法选择删除 ID。")
        record["query_hits_before_delete"] = [hit.model_dump(mode="json") for hit in hits]
        print("query:", args.query)
        for rank, hit in enumerate(hits, start=1):
            print(json.dumps({
                "rank": rank, "id": hit.source_id, "content": hit.content,
                "file": hit.file_path, "page": hit.page, "score": hit.score,
                "distance": hit.metadata["_retrieval"]["distance"],
            }, ensure_ascii=False))

        deleted_id = hits[0].source_id
        record["deleted_id"] = deleted_id
        save_record(record_path, record)
        index.delete([deleted_id])
        record["count_after_delete"] = index.count()
        require(index.count() == len(sources) - 1, "删除后计数不是 N-1。")
        deleted = index.collection.get(ids=[deleted_id])
        require(deleted["ids"] == [], "按精确 ID 查询仍能找到被删除记录。")
        after_hits = index.search(args.query, top_k=3)
        require(all(hit.source_id != deleted_id for hit in after_hits), "检索仍返回已删除 ID。")
        record["query_ids_after_delete"] = [hit.source_id for hit in after_hits]
        expected = snapshot([source for source in sources if source.source_id != deleted_id])
        require(snapshot(index.all()) == expected, "删除后其余正文或元数据发生变化。")
        record["remaining_sources"] = expected
        record["status"] = "built_and_deleted"
        save_record(record_path, record)
    except Exception as exc:
        record.update(status="failed", error_type=type(exc).__name__, reason=str(exc))
        save_record(record_path, record)
        raise

    for key in ("original_count", "count_after_first_add", "count_after_second_add", "count_after_delete", "deleted_id"):
        print(f"{key}:", record[key])
    print("record:", record_path)
    print("BUILD PASS：本进程结束后，以相同 --version 运行 reopen。")


def reopen(db_path: Path, name: str, record_path: Path) -> None:
    # 此分支不加载语料、不加载模型、不调用 add，也不创建缺失的集合。
    require(record_path.is_file(), "找不到实验记录；请先运行 build。")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    require(record.get("status") == "built_and_deleted", "build 未成功完成，不能验证持久化。")
    require(record["database_path"] == str(db_path) and record["collection_name"] == name,
            "实验记录与数据库路径或集合名不匹配。")
    require((db_path / "chroma.sqlite3").is_file(), "数据库文件不存在。")

    import chromadb

    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_collection(name=name, embedding_function=None)
    require((collection.configuration.get("hnsw") or {}).get("space") == "cosine",
            "集合距离配置不匹配。")
    count = collection.count()
    require(count == record["original_count"] - 1, "重启后计数不是 N-1。")
    require(collection.get(ids=[record["deleted_id"]])["ids"] == [], "重启后删除的 ID 恢复了。")
    result = collection.get(include=["documents", "metadatas"])
    restored = ChromaIndex._sources_from_get(result)
    require(snapshot(restored) == record["remaining_sources"], "重启后剩余正文或来源信息与快照不一致。")

    verification = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "count": count,
        "remaining_ids": sorted(source.source_id for source in restored),
        "deleted_id_absent": True,
        "sources_match_snapshot": True,
    }
    record.setdefault("reopen_checks", []).append(verification)
    save_record(record_path, record)
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    print("REOPEN PASS：未重新加载语料或 add，数据与删除状态均已持久化。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "reopen"])
    parser.add_argument("--version", default="v1", help="新实验使用新版本，例如 v2")
    parser.add_argument("--document-root", type=Path,
                        default=PROJECT_ROOT / "data" / "day07" / "input")
    parser.add_argument("--query", default="tools and parameters",
                        help="build 查询主题；默认对应 Day 07 PDF 测试语料")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", args.version):
        parser.error("--version 仅允许小写字母、数字和连字符，长度 1～40")
    if not args.query.strip():
        parser.error("--query 不能为空白")

    folder = PROJECT_ROOT / "data" / "day08" / f"persistence-{args.version}"
    db_path = folder / "chroma"
    name = f"day08-persistence-{args.version}"
    record_path = folder / "experiment.json"
    if args.mode == "build":
        build(args, db_path, name, record_path)
    else:
        reopen(db_path, name, record_path)


if __name__ == "__main__":
    main()
