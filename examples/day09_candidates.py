"""两路检索演示：支持类型/文件过滤，--fuse 输出 RRF，--smoke 使用受控向量。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.models import Source
from research_agent.retrieval import ChromaIndex, KeywordIndex
from research_agent.retrieval_pipeline import LazyCandidateIndex, TwoBranchRetriever
from research_agent.source_filters import normalize_filters


class SmokeEmbedder:
    """只验证接口和存储链路，不用于语义检索效果比较。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        mapping = {"offset": [1.0, 0.0], "max_steps": [0.0, 1.0],
                   "model_name": [0.6, 0.8]}
        return [mapping[text.split()[0]] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="offset")
    parser.add_argument("--candidate-k", type=int, default=6)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--allowed-id", action="append", default=None,
                        help="允许的 source_id；可重复提供，不传表示允许全部")
    parser.add_argument("--file-type", action="append", choices=["txt", "markdown", "pdf"],
                        help="允许的文件类型，可重复提供；字段间按 AND 组合")
    parser.add_argument("--relative-path", action="append",
                        help="语料内相对文件路径，可重复提供")
    parser.add_argument("--fuse", action="store_true", help="召回后执行 RRF，填充 final_sources")
    parser.add_argument("--smoke", action="store_true", help="受控假向量，仅验证接口")
    parser.add_argument("--allow-degraded", action="store_true", help="显式允许单路运行故障后使用另一分支")
    parser.add_argument("--query-id", help="实验问题 ID；不传则自动生成")
    parser.add_argument("--output-root", type=Path, default=(
        Path(__file__).resolve().parents[1] / "data/day09/candidates"
    ))
    parser.add_argument("--dataset", type=Path, default=(
        Path(__file__).resolve().parents[1] / "data/day08/retrieval-v1"
    ))
    args = parser.parse_args()
    filters = {}
    if args.file_type is not None:
        filters["file_types"] = set(args.file_type)
    if args.relative_path is not None:
        filters["relative_paths"] = set(args.relative_path)
    filters = normalize_filters(filters)

    if args.smoke:
        sources = [Source(source_id=name, title=name, content=content) for name, content in [
            ("doc-offset", "offset 记录原文位置"),
            ("doc-steps", "max_steps 限制执行次数"),
            ("doc-model", "model_name 指定模型名称"),
        ]]
        mode, fingerprint = "smoke_controlled_vectors_not_semantic_evaluation", None
    else:
        # 复用 Day 08 固定数据校验，不移动文件、不重新编号。
        if __package__:
            from .day08_evaluate_retrieval import load_fixed_dataset
        else:
            from day08_evaluate_retrieval import load_fixed_dataset
        manifest, _, sources = load_fixed_dataset(args.dataset)
        config = manifest["config"]
        mode, fingerprint = "real_embedding", manifest["fingerprint"]

    # 每次运行独立目录，保留实验结果；Windows 下不在连接存活时删除数据库。
    run_dir = args.output_root / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    keyword = KeywordIndex()
    keyword.add(sources)

    def prepare_vector():
        embedder = SmokeEmbedder() if args.smoke else SentenceTransformerEmbedder(
            model_name=config["model"], device="cpu",
            revision=config["resolved_model_commit"],
            query_instruction=config["query_instruction"],
        )
        vector = ChromaIndex(run_dir / "chroma", collection_name="day09-candidates-v1",
                             embedder=embedder)
        vector.add(sources)
        return vector

    vector = LazyCandidateIndex(prepare_vector)
    retriever = TwoBranchRetriever(sources, keyword_index=keyword, vector_index=vector)
    search = retriever.search if args.fuse else retriever.retrieve_candidates
    result = search(
        args.query, candidate_k=args.candidate_k, top_k=args.top_k,
        allowed_ids=set(args.allowed_id) if args.allowed_id is not None else None,
        filters=filters, allow_degraded=args.allow_degraded, query_id=args.query_id,
    )
    payload = {"mode": mode, "query": args.query, "run_dir": str(run_dir),
               "dataset_fingerprint": fingerprint, "result": asdict(result)}
    output = json.dumps(payload, ensure_ascii=False, indent=2,
                        default=lambda value: value.model_dump(mode="json"), allow_nan=False)
    (run_dir / "candidates.json").write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
