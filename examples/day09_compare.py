"""阶段八：固定数据真实三组对比；run 保存候选，report 根据正文审核生成成绩。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from research_agent.comparison import (
    REVIEW_FIELDS, TimedCandidateIndex, aggregate_comparison, compare_query,
    make_review_rows, render_comparison_report,
)
from research_agent.context import build_context
from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.models import Source
from research_agent.retrieval import ChromaIndex, KeywordIndex
from research_agent.retrieval_errors import RetrievalOperationalError
from research_agent.retrieval_pipeline import TwoBranchRetriever
from research_agent.source_filters import normalize_filters, resolve_allowed_ids

if __package__:
    from .day08_evaluate_retrieval import load_fixed_dataset
    from .day08_prepare_retrieval_dataset import audit_lengths, read_jsonl, resolve_labels
else:
    from day08_evaluate_retrieval import load_fixed_dataset
    from day08_prepare_retrieval_dataset import audit_lengths, read_jsonl, resolve_labels


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data/day08/retrieval-v1"
DEFAULT_CHALLENGES = ROOT / "curriculum/day09-challenge-v1.jsonl"


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                              default=lambda item: item.model_dump(mode="json")) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_questions(labels: dict, sources: list[Source], challenges: Path) -> list[dict]:
    """完整保留原10+2题，独立解析挑战版本；检索前验证支持句与过滤范围。"""
    entries = [dict(entry, group="baseline", has_allowed_evidence=True, filters={})
               for entry in labels["questions"]]
    entries += [dict(entry, group="baseline", has_allowed_evidence=False, filters={})
                for entry in labels["probes"]]
    challenge_entries = read_jsonl(challenges)
    if not 4 <= len(challenge_entries) <= 6:
        raise ValueError("挑战组应为4～6题，请另存版本")
    for entry in challenge_entries:
        raw_filters = entry.get("filters", {})
        if (not isinstance(raw_filters, dict)
                or any(not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                       for values in raw_filters.values())):
            raise ValueError("挑战题 filters 必须是字符串数组字段")
        normalized = normalize_filters({name: set(values) for name, values in raw_filters.items()})
        if type(entry.get("has_allowed_evidence")) is not bool:
            raise ValueError("必须显式声明 has_allowed_evidence 为 bool")
        resolved = resolve_labels(sources, [entry])[0]
        allowed = resolve_allowed_ids(sources, normalized)
        acceptable = resolved["acceptable_source_ids"]
        has_evidence = bool(acceptable if allowed is None else set(acceptable) & allowed)
        if has_evidence != entry["has_allowed_evidence"]:
            raise ValueError(f"{entry['query_id']} 的过滤后证据声明与预先固定的支持句不一致")
        entries.append({**resolved, "group": "challenge",
                        "filters": {name: sorted(values) for name, values in normalized.items()},
                        "acceptable_source_ids": [sid for sid in acceptable if allowed is None or sid in allowed]})
    ids = [entry["query_id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("基线和挑战题 query_id 不能重复")
    return entries


def save_review(run_dir: Path, raw: dict) -> None:
    """仅在新运行中创建空审核表，report 不覆盖用户已填写的表。"""
    with (run_dir / "review.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(make_review_rows(raw))


def report(run_dir: Path) -> dict:
    """检查原始结果完整性与审核表不可变字段，保存独立报告修订快照。"""
    integrity = json.loads((run_dir / "raw_integrity.json").read_text(encoding="utf-8"))
    if digest(run_dir / "raw_results.json") != integrity["sha256"]:
        raise ValueError("原始结果被修改；请启动新运行，不要覆盖旧结果")
    raw = json.loads((run_dir / "raw_results.json").read_text(encoding="utf-8"))
    with (run_dir / "review.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != REVIEW_FIELDS:
            raise ValueError("review.csv 列名或顺序不匹配")
        rows = list(reader)
    summary = aggregate_comparison(raw, rows)
    history = run_dir / "reports"
    history.mkdir(exist_ok=True)
    revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    write_json(history / f"{revision}.json", {"summary": summary, "review_rows": rows})
    write_json(run_dir / "summary.json", summary)
    (run_dir / "report.md").write_text(render_comparison_report(raw, summary, rows), encoding="utf-8")
    return summary


def run_comparison(
    dataset: Path = DEFAULT_DATASET, challenges: Path = DEFAULT_CHALLENGES, *,
    output_root: Path = ROOT / "data/day09/comparison", candidate_k: int = 6,
    max_context_chars: int = 2000, note: str = "initial three-way comparison",
) -> Path:
    """真实模型只加载一次，独立Day09集合只建一次；原语料/题目不写入。"""
    if type(candidate_k) is not int or candidate_k < 3:
        raise ValueError("candidate_k 必须是至少为3的整数")
    build_context([], max_context_chars=max_context_chars)
    manifest, labels, sources = load_fixed_dataset(dataset)
    entries = load_questions(labels, sources, challenges)
    run_dir = output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run_dir.mkdir(parents=True, exist_ok=False)
    config = manifest["config"]
    frozen = {"dataset_manifest": manifest, "challenge_sha256": digest(challenges),
              "challenge_file": str(challenges.resolve()), "questions": entries,
              "candidate_k": candidate_k, "top_k": 3, "rank_constant": 60,
              "max_context_chars": max_context_chars, "allow_degraded": False,
              "note": note, "model": config}
    write_json(run_dir / "config.json", frozen)  # 在任何查询前固定题目、证据和配置。
    startup = {}
    try:
        started = perf_counter()
        embedder = SentenceTransformerEmbedder(
            model_name=config["model"], revision=config["resolved_model_commit"], device="cpu",
            query_instruction=config["query_instruction"],
        )
        startup["model_load_ms"] = (perf_counter() - started) * 1000
        audit = audit_lengths(embedder, sources, entries)
        write_json(run_dir / "length_audit.json", audit)
        if (audit["model_limit"] != config["model_limit"] or audit["over_limit_document_count"]
                or audit["over_limit_query_count"]):
            raise ValueError("模型长度审计不通过")
        started = perf_counter()
        keyword = KeywordIndex()
        keyword.add(sources)
        startup["keyword_build_ms"] = (perf_counter() - started) * 1000
        started = perf_counter()
        vector = ChromaIndex(run_dir / "chroma", collection_name="day09-comparison-v1", embedder=embedder)
        vector.add(sources)
        startup["vector_build_ms"] = (perf_counter() - started) * 1000
        indexes = {"keyword": TimedCandidateIndex(keyword), "vector": TimedCandidateIndex(vector)}
        started = perf_counter()
        retriever = TwoBranchRetriever(sources, keyword_index=indexes["keyword"], vector_index=indexes["vector"])
        startup["coordinator_validation_ms"] = (perf_counter() - started) * 1000
        # 明确预热：用固定基线首题，每路一次，不计入正式查询或命中统计。
        startup["warmup_question_id"] = entries[0]["query_id"]
        for name, index in indexes.items():
            index.search(entries[0]["question"], top_k=min(candidate_k, len(sources)))
            startup[name + "_warmup_ms"] = index.last_search_ms
        queries = [compare_query(retriever, sources, entry, candidate_k=candidate_k,
                                 max_context_chars=max_context_chars, timed_indexes=indexes)
                   for entry in entries]
    except RetrievalOperationalError as exc:
        # 初始化/预热失败时实验未成立；保留原因并抛出，不回退假模型或静默继续。
        write_json(run_dir / "failure.json", {"status": "failed", "error_type": exc.error_type,
                                             "reason": str(exc), "startup": startup})
        raise
    raw = {"run_id": run_dir.name, "mode": "real_embedding_three_way_comparison",
           "dataset_fingerprint": manifest["fingerprint"],
           "challenge_sha256": frozen["challenge_sha256"], "config": frozen,
           "startup": startup, "candidate_k": candidate_k, "top_k": 3, "rank_constant": 60,
           "max_context_chars": max_context_chars, "source_count": len(sources),
           "versions": {name: version(name) for name in ("chromadb", "sentence-transformers", "transformers")},
           "canonical_sources": [source.model_dump(mode="json") for source in sources], "queries": queries}
    write_json(run_dir / "raw_results.json", raw)
    write_json(run_dir / "raw_integrity.json", {"sha256": digest(run_dir / "raw_results.json")})
    save_review(run_dir, raw)
    report(run_dir)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["run", "report"], default="run")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--challenges", type=Path, default=DEFAULT_CHALLENGES)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/day09/comparison")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--candidate-k", type=int, default=6)
    parser.add_argument("--max-context-chars", type=int, default=2000)
    parser.add_argument("--note", default="initial three-way comparison")
    args = parser.parse_args()
    if args.mode == "run":
        path = run_comparison(args.dataset_root, args.challenges, output_root=args.output_root,
                              candidate_k=args.candidate_k, max_context_chars=args.max_context_chars,
                              note=args.note)
    else:
        if args.run_dir is None:
            parser.error("report 需要 --run-dir")
        path = args.run_dir
        report(path)
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    print(f"Run directory: {path}\nPending candidate rows: {summary['pending_candidate_rows']}")
    print(f"Failed questions: {summary['failed_query_ids']}")
    print("填写 review.csv 后运行 report；不得将预标注ID命中率当成人工正文支持率。")


if __name__ == "__main__":
    main()
