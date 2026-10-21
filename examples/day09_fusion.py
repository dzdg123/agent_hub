"""阶段三：手算案例，或复用 candidates.json 比较 RRF 与两种 min-max 策略。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from research_agent.fusion import FusionResult, fuse_min_max, fuse_rrf
from research_agent.models import Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_demo() -> tuple[list[Source], dict[str, list[Source]]]:
    """固定 A/B/C 与 B/D/A，分数仅供 min-max 对照。"""
    canonical = [Source(source_id=name, title=name, content=f"content {name}") for name in "ABCD"]
    lookup = {source.source_id: source for source in canonical}
    branches = {
        name: [lookup[source_id].model_copy(deep=True, update={"score": score})
               for source_id, score in pairs]
        for name, pairs in {
            "keyword": [("A", 0.9), ("B", 0.6), ("C", 0.2)],
            "vector": [("B", 0.7), ("D", 0.5), ("A", -0.1)],
        }.items()
    }
    return canonical, branches


def load_saved_candidates(
    path: Path, dataset: Path,
) -> tuple[dict, list[Source], dict[str, list[Source]]]:
    """只读原候选；真实实验重新验证固定资料和指纹，不重新调用 Embedding。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload["result"].get("status") in {"degraded", "failed"}
            or any(branch.get("status") == "failed"
                   for branch in payload["result"]["branches"].values())):
        raise ValueError("降级或失败候选不能用于完整双路融合对照；请使用独立降级统计")
    branches = {
        name: [Source.model_validate(record) for record in branch["sources"]]
        for name, branch in payload["result"]["branches"].items()
    }
    if payload["mode"] == "real_embedding":
        if __package__:
            from .day08_evaluate_retrieval import load_fixed_dataset
        else:
            from day08_evaluate_retrieval import load_fixed_dataset
        manifest, _, canonical = load_fixed_dataset(dataset)
        if payload["dataset_fingerprint"] != manifest["fingerprint"]:
            raise ValueError("候选文件与规范资料的 fingerprint 不一致")
    elif payload["mode"] == "smoke_controlled_vectors_not_semantic_evaluation":
        canonical = [Source(source_id=name, title=name, content=content) for name, content in [
            ("doc-offset", "offset 记录原文位置"),
            ("doc-steps", "max_steps 限制执行次数"),
            ("doc-model", "model_name 指定模型名称"),
        ]]
    else:
        raise ValueError("仅支持阶段二真实模型或受控向量候选文件")
    return payload, canonical, branches


def compare_fusions(
    branches: dict[str, list[Source]], canonical_sources: list[Source], *,
    top_k: int = 3, rank_constant: int = 60,
) -> dict[str, FusionResult]:
    """对同一份候选分别融合，三个结果及轨迹互相独立。"""
    return {
        "rrf": fuse_rrf(branches, canonical_sources=canonical_sources,
                        top_k=top_k, rank_constant=rank_constant),
        "min_max_equal_1": fuse_min_max(branches, canonical_sources=canonical_sources,
                                        top_k=top_k, equal_score_value=1),
        "min_max_equal_0": fuse_min_max(branches, canonical_sources=canonical_sources,
                                        top_k=top_k, equal_score_value=0),
    }


def normalization_examples() -> dict:
    """固定展示：低分单候选被赋 1、同分策略改变排名、窗口改变归一化值。"""
    canonical, _ = make_demo()
    lookup = {source.source_id: source for source in canonical}

    def hit(name: str, score: float) -> Source:
        return lookup[name].model_copy(deep=True, update={"score": score})

    singleton = {"keyword": [hit("A", 0.001)], "vector": [hit("B", 0.9), hit("D", 0.3)]}
    vector = [hit("A", 0.9), hit("B", 0.8), hit("C", 0.1)]
    return {
        "singleton_policy": {
            str(equal): asdict(fuse_min_max(singleton, canonical_sources=canonical,
                                            equal_score_value=equal)) for equal in (1, 0)
        },
        "candidate_window": {
            str(k): asdict(fuse_min_max({"vector": vector[:k]}, canonical_sources=canonical))
            for k in (2, 3)
        },
        "note": "同分赋值是教学约定；归一化和 RRF 分数都不是证据可信度或答案正确概率。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo", action="store_true", help="固定手算案例（默认）")
    group.add_argument("--candidates-json", type=Path, help="复用阶段二候选文件")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--rank-constant", type=int, default=60)
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data/day08/retrieval-v1")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data/day09/fusion")
    args = parser.parse_args()
    if args.candidates_json:
        original, canonical, branches = load_saved_candidates(args.candidates_json, args.dataset)
        mode, query = original["mode"], original["query"]
        input_info = {"mode": mode, "query": query, "candidate_file": str(args.candidates_json),
                      "dataset_fingerprint": original.get("dataset_fingerprint"),
                      "requested_candidate_k": original["result"]["requested_candidate_k"],
                      "effective_candidate_k": original["result"]["effective_candidate_k"]}
    else:
        canonical, branches = make_demo()
        input_info = {"mode": "synthetic_hand_calculation", "query": None}
    results = compare_fusions(branches, canonical, top_k=args.top_k,
                              rank_constant=args.rank_constant)
    payload = {"input": input_info, "candidate_snapshot": branches,
               "results": {name: asdict(result) for name, result in results.items()},
               "normalization_examples": normalization_examples()}
    output = json.dumps(payload, ensure_ascii=False, indent=2,
                        default=lambda value: value.model_dump(mode="json"), allow_nan=False)
    run_dir = args.output_root / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    path = run_dir / "fusion.json"
    path.write_text(output + "\n", encoding="utf-8")
    for name, result in results.items():
        print(name + ": " + " > ".join(
            f"{source.title} ({source.score:.6f})" for source in result.sources
        ))
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
