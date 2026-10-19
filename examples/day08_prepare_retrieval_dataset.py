"""阶段七：加载固定语料、审计长度并从人工关键句派生可接受的 Source ID。"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Any

from research_agent.documents import load_all_documents_detailed, normalize_document_text
from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.models import Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "data/day08/retrieval-v1"
CHUNK_SIZE = 400
OVERLAP = 60
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{number} JSON 格式错误") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{number} 必须是对象")
        rows.append(row)
    ids = [row.get("query_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in ids):
        raise ValueError(f"{path.name} 缺少有效 query_id")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name} 存在重复 query_id")
    return rows


def resolve_labels(sources: list[Source], questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = []
    for question in questions:
        query_id = question["query_id"]
        path = question.get("expected_relative_path")
        quote = question.get("evidence_quote")
        if not isinstance(question.get("question"), str) or not question["question"].strip():
            raise ValueError(f"{query_id}: 问题不能为空")
        if not isinstance(path, str) or not path or "\\" in path:
            raise ValueError(f"{query_id}: 使用有效的 POSIX 相对文件路径")
        relative = PurePosixPath(path)
        if relative.is_absolute() or ".." in relative.parts or ":" in path:
            raise ValueError(f"{query_id}: 证据文件必须位于 corpus 内")
        if "expected_page" not in question:
            raise ValueError(f"{query_id}: 缺少 expected_page，文本文件请显式填 null")
        page = question["expected_page"]
        if relative.suffix.lower() == ".pdf":
            if type(page) is not int or page <= 0:
                raise ValueError(f"{query_id}: PDF 标签需要正整数物理页号")
        elif page is not None:
            raise ValueError(f"{query_id}: 文本文件 expected_page 必须为 null")
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError(f"{query_id}: 缺少支持结论的 evidence_quote")
        normalized_quote = normalize_document_text(quote)
        matches = [
            source for source in sources
            if source.metadata.get("relative_path") == path
            and source.page == page
            and normalized_quote in source.content
        ]
        if not matches:
            raise ValueError(
                f"{query_id}: {path} page={page} 没有片段完整包含关键句；"
                "检查人工标注、切片边界，或明确标注所需的片段组合，不能猜测 Source ID"
            )
        resolved.append({
            **question,
            "normalized_evidence_quote": normalized_quote,
            "acceptable_source_ids": sorted(source.source_id for source in matches),
            "matching_rule": "same_file_and_physical_page_contains_full_quote",
        })
    return resolved


def audit_lengths(
    embedder: SentenceTransformerEmbedder,
    sources: list[Source],
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    limit = int(embedder.model.max_seq_length)
    documents = [{
        "source_id": source.source_id,
        "relative_path": source.metadata["relative_path"],
        "page": source.page,
        "character_count": len(source.content),
        "token_count": embedder.token_length(source.content),
    } for source in sources]
    queries = [{
        "query_id": row["query_id"],
        "token_count": embedder.token_length(
            (embedder.query_instruction or "") + row["question"]
        ),
    } for row in questions]
    return {
        "model_limit": limit,
        "max_document_tokens": max((row["token_count"] for row in documents), default=0),
        "over_limit_document_count": sum(row["token_count"] > limit for row in documents),
        "max_query_tokens": max((row["token_count"] for row in queries), default=0),
        "over_limit_query_count": sum(row["token_count"] > limit for row in queries),
        "includes_special_tokens": True,
        "documents": documents,
        "queries": queries,
    }


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def resolved_model_commit(embedder: SentenceTransformerEmbedder, revision: str | None) -> str:
    commit = getattr(embedder.model[0].auto_model.config, "_commit_hash", None)
    if commit:
        return commit
    # 某些 transformers 版本不保留 _commit_hash，从实际本地缓存快照解析。
    # 此调用只读缓存，不访问 HF Hub。
    from huggingface_hub import try_to_load_from_cache

    cached = try_to_load_from_cache(MODEL_NAME, "config.json", revision=revision or "main")
    if isinstance(cached, str):
        config_path = Path(cached)
        if config_path.parent.parent.name == "snapshots":
            return config_path.parent.name
    raise ValueError("无法确认实际模型快照，不能将未知模型版本混入固定评测配置")


def prepare(root: Path, revision: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    questions = read_jsonl(root / "questions.jsonl")
    probes = read_jsonl(root / "probes.jsonl")
    if {row["query_id"] for row in questions} != {f"Q{i:02}" for i in range(1, 11)}:
        raise ValueError("需要固定 Q01～Q10 共 10 道正向问题")
    if {row["query_id"] for row in probes} != {"N01", "N02"}:
        raise ValueError("需要 N01、N02 两道独立无证据探针")
    for probe in probes:
        if (probe.get("has_evidence") is not False
                or probe.get("include_in_positive_hit_rate") is not False
                or not isinstance(probe.get("question"), str)
                or not probe["question"].strip()
                or not probe.get("reason")):
            raise ValueError("探针需明确没有目标答案、说明原因，并排除在正向命中率分母之外")

    result = load_all_documents_detailed(root / "corpus", chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    if result.errors:
        raise ValueError(f"语料加载失败：{[asdict(error) for error in result.errors]}")
    if not 8 <= result.loaded_files <= 12 or len(result.sources) < 12:
        raise ValueError(f"要求 8～12 份资料且至少 12 个片段，实际 {result.loaded_files} 份/{len(result.sources)} 片")
    ids = [source.source_id for source in result.sources]
    if len(ids) != len(set(ids)):
        raise ValueError("加载器生成了重复 Source ID")
    resolved = resolve_labels(result.sources, questions)

    embedder = SentenceTransformerEmbedder(model_name=MODEL_NAME, revision=revision, device="cpu")
    audit = audit_lengths(embedder, result.sources, questions + probes)
    if audit["over_limit_document_count"] or audit["over_limit_query_count"]:
        save_json(root / "length_audit.json", audit)
        raise ValueError("长度审计失败，详见 length_audit.json；调整切片后使用新语料版本")

    config = {
        "model": MODEL_NAME,
        "requested_revision": revision,
        "resolved_model_commit": resolved_model_commit(embedder, revision),
        "sentence_transformers_version": version("sentence-transformers"),
        "transformers_version": version("transformers"),
        "normalize_embeddings": True,
        "query_instruction": None,
        "chunk_size": CHUNK_SIZE,
        "overlap": OVERLAP,
        "model_limit": audit["model_limit"],
    }
    inputs = sorted((root / "corpus").rglob("*")) + [root / "questions.jsonl", root / "probes.jsonl"]
    hashes = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in inputs if path.is_file()
    }
    fingerprint = hashlib.sha256(json.dumps(
        {"files": hashes, "config": config}, sort_keys=True, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    manifest_path = root / "dataset_manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("fingerprint") != fingerprint:
            raise ValueError("固定数据或模型配置已改变，请复制到新语料版本目录再生成标签")

    # 标签只由文件、物理页及完整关键句派生，不运行任何检索。
    save_json(root / "length_audit.json", audit)
    save_json(root / "resolved_labels.json", {
        "fingerprint": fingerprint,
        "corpus_root": str(root / "corpus"),
        "positive_question_count": 10,
        "questions": resolved,
        "probes": probes,
        "note": "acceptable_source_ids 依赖本机绝对路径和切片配置；移动目录后重新派生",
    })
    with (root / "sources.jsonl").open("w", encoding="utf-8") as output:
        for source in result.sources:
            output.write(source.model_dump_json() + "\n")
    manifest = {
        "dataset_version": root.name,
        "fingerprint": fingerprint,
        "config": config,
        "file_sha256": hashes,
        "loaded_files": result.loaded_files,
        "source_count": len(result.sources),
        "positive_question_count": len(questions),
        "no_evidence_probe_count": len(probes),
        "positive_hit_rate_denominator": 10,
        "loader_warnings": [asdict(warning) for warning in result.warnings],
    }
    save_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--revision", default=None, help="可选模型快照 SHA；实际解析 SHA 会记录到清单")
    args = parser.parse_args()
    manifest = prepare(args.dataset_root, args.revision)
    print(json.dumps({key: manifest[key] for key in (
        "dataset_version", "loaded_files", "source_count", "positive_question_count",
        "no_evidence_probe_count", "positive_hit_rate_denominator",
    )}, ensure_ascii=False, indent=2))
    print("PREPARE PASS：长度审计和证据句定位通过，未运行检索或调整人工标签。")
    print("output:", args.dataset_root.resolve())


if __name__ == "__main__":
    main()
