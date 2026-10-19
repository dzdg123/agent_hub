"""阶段八：保存真实 Top-3，生成待人工审核的 CSV，再计算人工 Hit@3。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4

from research_agent.documents import load_all_documents_detailed
from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.retrieval import ChromaIndex

if __package__:
    from .day08_prepare_retrieval_dataset import resolve_labels, read_jsonl, audit_lengths
else:
    from day08_prepare_retrieval_dataset import resolve_labels, read_jsonl, audit_lengths


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data/day08/retrieval-v1"
DEFAULT_OUTPUT = PROJECT_ROOT / "data/day08/retrieval-evaluation"
FIELDS = [
    "query_id", "question", "kind", "expected_relative_path", "expected_page",
    "evidence_quote", "rank", "source_id", "relative_path", "file_path", "page",
    "content", "distance", "score", "preannotated_evidence_match",
    "support_level", "reason", "error_cause",
]
EDITABLE = {"support_level", "reason", "error_cause"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixed_dataset(root: Path) -> tuple[dict, dict, list]:
    manifest = read_json(root / "dataset_manifest.json")
    labels = read_json(root / "resolved_labels.json")
    config = manifest["config"]
    actual_inputs = {
        path.relative_to(root).as_posix()
        for path in (root / "corpus").rglob("*") if path.is_file()
    } | {"questions.jsonl", "probes.jsonl"}
    if actual_inputs != set(manifest["file_sha256"]):
        raise ValueError("语料文件集合已变化，请准备新语料版本")
    for relative_path, expected_hash in manifest["file_sha256"].items():
        if digest(root / relative_path) != expected_hash:
            raise ValueError(f"固定输入已变化：{relative_path}；请准备新版本，不要改旧标签")
    fingerprint = hashlib.sha256(json.dumps(
        {"files": manifest["file_sha256"], "config": config},
        sort_keys=True, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    if fingerprint != manifest["fingerprint"] or fingerprint != labels["fingerprint"]:
        raise ValueError("配置指纹与派生标签不一致")
    for package, key in (("sentence-transformers", "sentence_transformers_version"),
                         ("transformers", "transformers_version")):
        if version(package) != config[key]:
            raise ValueError(f"{package} 版本已变化，请准备新的实验版本")
    if config["normalize_embeddings"] is not True or config["query_instruction"] is not None:
        raise ValueError("当前脚本只运行阶段七固定的归一化、无查询指令基线")
    loaded = load_all_documents_detailed(
        root / "corpus", chunk_size=config["chunk_size"], overlap=config["overlap"],
    )
    if loaded.errors:
        raise ValueError(f"文档加载失败：{loaded.errors}")
    if len(loaded.sources) != manifest["source_count"] or len(loaded.sources) < 12:
        raise ValueError("片段数与固定清单不一致")
    questions = read_jsonl(root / "questions.jsonl")
    probes = read_jsonl(root / "probes.jsonl")
    if (len(questions) != 10 or len(probes) != 2
            or manifest["positive_hit_rate_denominator"] != 10):
        raise ValueError("评测必须保留 10 道正向题及 2 道探针")
    if resolve_labels(loaded.sources, questions) != labels["questions"] or probes != labels["probes"]:
        raise ValueError("派生 ID 或标签已过期，请先重新运行阶段七脚本")
    return manifest, labels, loaded.sources


def review_rows(raw: dict) -> list[dict[str, Any]]:
    rows = []
    for query in raw["queries"]:
        for candidate in query["candidates"]:
            rows.append({
                "query_id": query["query_id"], "question": query["question"],
                "kind": query["kind"],
                "expected_relative_path": query.get("expected_relative_path", ""),
                "expected_page": query.get("expected_page") or "",
                "evidence_quote": query.get("evidence_quote", ""),
                **candidate,
                "page": candidate["page"] or "",
                "support_level": "", "reason": "", "error_cause": "",
            })
    return rows


def aggregate(raw: dict, rows: list[dict[str, str]]) -> dict:
    expected = review_rows(raw)
    if len(rows) != len(expected):
        raise ValueError("审核表候选行数变化，不能删除失败题或候选")
    by_key = {}
    for row in rows:
        key = (row["query_id"], row["rank"])
        if key in by_key:
            raise ValueError("审核表有重复问题/排名")
        by_key[key] = row
    graded = []
    for original in expected:
        key = (original["query_id"], str(original["rank"]))
        if key not in by_key:
            raise ValueError(f"审核表缺失候选 {key}")
        row = by_key[key]
        for field in set(FIELDS) - EDITABLE:
            if row.get(field) != str(original[field]):
                raise ValueError(f"{key} 的 {field} 已修改；仅填写等级、理由、错误原因")
        level = row["support_level"].strip()
        if level and level not in {"0", "1", "2"}:
            raise ValueError(f"{key} 的支持等级必须为 0、1、2 或留空")
        if level and not row["reason"].strip():
            raise ValueError(f"{key} 已评分但缺少正文判断理由")
        graded.append({**row, "support_level": int(level) if level else None})

    per_query = []
    for query in raw["queries"]:
        candidates = [row for row in graded if row["query_id"] == query["query_id"]]
        complete = bool(candidates) and all(row["support_level"] is not None for row in candidates)
        hit = int(any(row["support_level"] == 2 for row in candidates)) if complete else None
        per_query.append({
            "query_id": query["query_id"], "kind": query["kind"],
            "review_complete": complete, "manual_hit_at_3": hit,
            "support_levels": [row["support_level"] for row in candidates],
            "error_causes": [row["error_cause"] for row in candidates if row["error_cause"]],
        })
    positives = [row for row in per_query if row["kind"] == "positive"]
    complete = len(positives) == 10 and all(row["review_complete"] for row in positives)
    hits = sum(row["manual_hit_at_3"] or 0 for row in positives) if complete else None
    return {
        "positive_denominator": 10,
        "reviewed_positive_questions": sum(row["review_complete"] for row in positives),
        "pending_candidate_rows": sum(row["support_level"] is None for row in graded),
        "manual_hit_count": hits,
        "manual_hit_at_3": hits / 10 if hits is not None else None,
        "teaching_target_met": hits >= 8 if hits is not None else None,
        "preannotation_id_hit_at_3": raw["preannotation_id_hit_at_3"],
        "preannotation_note": "预标注证据 ID 命中率，仅作自动核对，不替代人工支持判断",
        "all_required_evidence_coverage": "当前每题只有一条必要关键句；不宣称多证据覆盖或 Recall@3",
        "per_query": per_query,
        "probe_warning": "N01/N02 不计入分母；近邻返回候选不代表存在答案，需人工记录不支持理由",
    }


def markdown_report(raw: dict, rows: list[dict], summary: dict) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")

    metric = summary["manual_hit_at_3"]
    lines = ["# Top-3 人工审核表", "",
             f"运行：{raw['run_id']}；固定正向分母：10；模型快照：{raw['config']['resolved_model_commit']}", "",
             "等级：0=无关或不支持；1=主题相关但缺关键证据；2=正文直接支持。", "",
             f"人工 Hit@3：{'待审核，尚未计分' if metric is None else str(summary['manual_hit_count']) + '/10'}", "",
             "编辑 review.csv 中 support_level、reason、error_cause 后运行 report；不要修改其他列。", ""]
    for query in raw["queries"]:
        lines.extend([f"## {query['query_id']}：{query['question']}", ""])
        if query["kind"] == "positive":
            lines.extend([f"预标注：{query['expected_relative_path']}，页：{query['expected_page']}。", "",
                          f"证据原句：{query['evidence_quote']}", ""])
        else:
            lines.extend([f"无目标答案探针：{query['reason']} 不计入命中率分母。", ""])
        lines.extend(["| 排名 | 来源 ID / 文件 / 页码 | 返回片段正文 | distance / score | 支持等级 | 理由 | 错误原因 |",
                      "| --- | --- | --- | --- | --- | --- | --- |"])
        for row in rows:
            if row["query_id"] != query["query_id"]:
                continue
            values = [row["rank"], f"{row['source_id']} / {row['relative_path']} / {row['page']}",
                      row["content"], f"{row['distance']} / {row['score']}",
                      row["support_level"] or "待填", row["reason"], row["error_cause"]]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
        lines.append("")
    lines.extend(["## 分析顺序", "",
                  "1. 核对证据是否加载、PDF 文字和物理页号是否正确。",
                  "2. 检查关键句是否被切开或输入是否超长。",
                  "3. 检查模型快照、归一化和问题预处理是否一致。",
                  "4. 检查 cosine 距离是否按从小到大排序。",
                  "5. 判断是否存在相似但不支持结论的干扰。",
                  "6. 再考虑模型表达能力和独立的查询指令对照实验。", "",
                  "每次修正运行保存在新目录，保留最初结果；不要删失败题或改原始标签。",
                  "Hit@3 不等于 Recall@3，也不是回答准确率；这 10 题只代表小规模教学实验。", ""])
    return "\n".join(lines)


def report(run_dir: Path) -> dict:
    integrity = read_json(run_dir / "raw_integrity.json")
    if digest(run_dir / "raw_results.json") != integrity["sha256"]:
        raise ValueError("原始检索结果被改动；请保留原始结果并启动新运行")
    raw = read_json(run_dir / "raw_results.json")
    with (run_dir / "review.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("审核表列名不匹配")
        rows = list(reader)
    summary = aggregate(raw, rows)
    history = run_dir / "reports"
    history.mkdir(exist_ok=True)
    revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    write_json(history / f"{revision}.json", {"summary": summary, "review_rows": rows})
    write_json(run_dir / "summary.json", summary)
    (run_dir / "review.md").write_text(markdown_report(raw, rows, summary), encoding="utf-8")
    return summary


def run(dataset_root: Path, output_root: Path, experiment_note: str) -> Path:
    manifest, labels, sources = load_fixed_dataset(dataset_root)
    config = manifest["config"]
    commit = config["resolved_model_commit"]
    if not commit:
        raise ValueError("请重新运行阶段七，记录实际模型快照")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    try:
        embedder = SentenceTransformerEmbedder(
            model_name=config["model"], revision=commit, device="cpu",
            query_instruction=config["query_instruction"],
        )
        audit = audit_lengths(embedder, sources, labels["questions"] + labels["probes"])
        write_json(run_dir / "length_audit.json", audit)
        if (audit["model_limit"] != config["model_limit"]
                or audit["over_limit_document_count"] or audit["over_limit_query_count"]):
            raise ValueError("实际模型长度审计与基线不一致")
        index = ChromaIndex(path=run_dir / "chroma", collection_name="day08-evaluation-cosine-v1",
                            embedder=embedder)
        index.add(sources)
        if index.count() != len(sources):
            raise RuntimeError("写入计数与语料不一致")
        queries = []
        for kind, entries in (("positive", labels["questions"]), ("probe", labels["probes"])):
            for entry in entries:
                candidates = []
                for rank, source in enumerate(index.search(entry["question"], top_k=3), start=1):
                    candidates.append({
                        "rank": rank, "source_id": source.source_id,
                        "relative_path": source.metadata["relative_path"],
                        "file_path": source.file_path or "", "page": source.page,
                        "content": source.content,
                        "distance": source.metadata["_retrieval"]["distance"],
                        "score": source.score,
                        "preannotated_evidence_match": source.source_id in entry.get("acceptable_source_ids", []),
                    })
                if len(candidates) != 3:
                    raise RuntimeError(f"{entry['query_id']} 未返回三条候选")
                queries.append({**entry, "kind": kind, "candidates": candidates})
        automatic_hits = sum(
            any(candidate["preannotated_evidence_match"] for candidate in query["candidates"])
            for query in queries if query["kind"] == "positive"
        )
        raw = {
            "run_id": run_id, "experiment_note": experiment_note,
            "dataset_fingerprint": manifest["fingerprint"], "config": config,
            "metric": "cosine", "top_k": 3, "source_count": index.count(),
            "chromadb_version": version("chromadb"),
            "preannotation_id_hit_at_3": automatic_hits / 10,
            "queries": queries,
        }
        write_json(run_dir / "raw_results.json", raw)
        write_json(run_dir / "raw_integrity.json", {"sha256": digest(run_dir / "raw_results.json")})
        write_json(run_dir / "dataset_manifest.json", manifest)
        with (run_dir / "review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(review_rows(raw))
        report(run_dir)
    except Exception as exc:
        write_json(run_dir / "failure.json", {"error_type": type(exc).__name__, "reason": str(exc)})
        raise
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["run", "report"], default="run")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-dir", type=Path, help="report 模式指定已填写审核表的运行目录")
    parser.add_argument("--note", default="initial baseline", help="修正实验请记录变更原因")
    args = parser.parse_args()
    if args.mode == "run":
        run_dir = run(args.dataset_root.resolve(), args.output_root.resolve(), args.note)
        print("run_dir:", run_dir)
    else:
        if args.run_dir is None:
            parser.error("report 需要 --run-dir 指定审核表所在的目录")
        run_dir = args.run_dir.resolve()
        report(run_dir)
    summary = read_json(run_dir / "summary.json")
    print(json.dumps({key: summary[key] for key in (
        "preannotation_id_hit_at_3", "reviewed_positive_questions", "pending_candidate_rows",
        "manual_hit_count", "manual_hit_at_3", "teaching_target_met",
    )}, ensure_ascii=False, indent=2))
    print("请填写 review.csv 的 support_level、reason、error_cause，再运行 report。")


if __name__ == "__main__":
    main()
