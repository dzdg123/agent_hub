"""阶段六：固定融合排名，逐步缩小字符预算，观察完整证据块的取舍。"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from research_agent.context import build_context, format_source_block, render_context
from research_agent.fusion import fuse_rrf
from research_agent.models import Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_demo() -> tuple[list[Source], dict[str, list[Source]]]:
    """三段不同长度、不同证据，同文件不同页，两个分支保持相同排名。"""
    canonical = []
    for page, (source_id, content) in enumerate([
        ("doc-offset", "offset 标记片段在原文中的起点。\n" * 30),
        ("doc-steps", "max_steps 限制代理最多执行多少步。\n" * 5),
        ("doc-model", "model_name 指定使用的模型。"),
    ], start=1):
        canonical.append(Source(
            source_id=source_id, title=f"教学手册第 {page} 页",
            file_path="guide.pdf", page=page, content=content,
            metadata={"offset": 120, "end_offset": 120 + len(content),
                      "offset_basis": "normalized_page_text", "chunk_index": 0},
        ))
    return canonical, {"keyword": canonical, "vector": canonical}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates-json", type=Path, help="复用阶段二候选，不重新生成 Embedding")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data/day08/retrieval-v1")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--budget", type=int, action="append", help="可重复指定；默认自动生成递减预算")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data/day09/context")
    args = parser.parse_args()
    if args.budget and any(budget <= 0 for budget in args.budget):
        parser.error("--budget 必须为正整数")
    if args.candidates_json:
        if __package__:
            from .day09_fusion import load_saved_candidates
        else:
            from day09_fusion import load_saved_candidates
        original, canonical, branches = load_saved_candidates(args.candidates_json, args.dataset)
        input_info = {"mode": original["mode"], "query": original["query"],
                      "candidate_file": str(args.candidates_json),
                      "dataset_fingerprint": original.get("dataset_fingerprint")}
    else:
        canonical, branches = make_demo()
        input_info = {"mode": "synthetic_context_budget"}

    before = deepcopy((canonical, branches))
    fusion = fuse_rrf(branches, canonical_sources=canonical, top_k=args.top_k)
    ranked = fusion.sources
    ranked_before = deepcopy(ranked)
    blocks = [format_source_block(source) for source in ranked]
    # 默认包含全部、排除最长块后保留短块、仅最短块和全部放不下四种情况。
    budgets = args.budget or sorted({
        max(2000, len(render_context(blocks))),
        max(1, len(render_context(blocks[1:]))),
        min((len(render_context([block])) for block in blocks), default=1),
        1,
    }, reverse=True)
    results = [build_context(ranked, max_context_chars=budget) for budget in budgets]
    unchanged = (canonical, branches) == before and ranked == ranked_before
    if not unchanged:
        raise AssertionError("上下文构建改变了规范来源、候选或融合结果")
    payload = {
        "input": input_info, "unit": "python_characters_not_model_tokens",
        "canonical_sources": canonical, "fusion": asdict(fusion),
        "inputs_unchanged": unchanged, "contexts": [asdict(result) for result in results],
    }
    run_dir = args.output_root / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    path = run_dir / "context.json"
    path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2,
        default=lambda value: value.model_dump(mode="json"), allow_nan=False,
    ) + "\n", encoding="utf-8")
    for result in results:
        print(f"\nBudget={result.budget}; used={result.used_chars}; status={result.status}")
        print(f"Included={result.included_source_ids}; omitted={result.omitted_source_ids}")
        print(result.text or "(无可放入的证据)")
    print(f"\nInputs unchanged: {unchanged}\nSaved: {path}")



if __name__ == "__main__":
    main()
