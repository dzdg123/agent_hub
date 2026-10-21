"""阶段五：演示精确 ID 去重、不同出处的重复正文和相邻片段重叠。"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from research_agent.fusion import fuse_rrf
from research_agent.models import Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_demo() -> tuple[list[Source], dict[str, list[Source]]]:
    canonical = [
        Source(source_id=name, title=f"{path} page {page} chunk {index}", content=content,
               file_path=path, page=page, metadata={
                   "offset": offset, "end_offset": offset + len(content),
                   "offset_basis": "normalized_page_text", "chunk_index": index,
               })
        for name, content, path, page, index, offset in [
            ("A", "abcdef", "guide.pdf", 1, 0, 0),
            ("B", "efghij", "guide.pdf", 1, 1, 4),
            ("C", "abcdef", "guide.pdf", 2, 0, 0),
            ("D", "abcdef", "archive.pdf", 9, 0, 0),
        ]
    ]
    lookup = {source.source_id: source for source in canonical}
    return canonical, {"keyword": [lookup[name] for name in "AABC"],
                       "vector": [lookup[name] for name in "BDA"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates-json", type=Path, help="不传则运行固定合成案例")
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "data/day08/retrieval-v1")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data/day09/dedup")
    args = parser.parse_args()
    if args.candidates_json:
        if __package__:
            from .day09_fusion import load_saved_candidates
        else:
            from day09_fusion import load_saved_candidates
        payload, canonical, branches = load_saved_candidates(args.candidates_json, args.dataset)
        input_info = {"mode": payload["mode"], "candidate_file": str(args.candidates_json),
                      "dataset_fingerprint": payload.get("dataset_fingerprint")}
    else:
        canonical, branches = make_demo()
        input_info = {"mode": "synthetic_provenance_demo"}
    original_sources, original_branches = deepcopy(canonical), deepcopy(branches)
    result = fuse_rrf(branches, canonical_sources=canonical, top_k=args.top_k)
    inputs_unchanged = canonical == original_sources and branches == original_branches
    if not inputs_unchanged:
        raise AssertionError("融合改变了规范来源或输入候选")
    output = json.dumps({"input": input_info, "candidate_snapshot": branches,
                         "inputs_unchanged": inputs_unchanged, "result": asdict(result)},
                        ensure_ascii=False, indent=2,
                        default=lambda value: value.model_dump(mode="json"), allow_nan=False)
    run_dir = args.output_root / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    path = run_dir / "dedup.json"
    path.write_text(output + "\n", encoding="utf-8")
    for rank, source in enumerate(result.sources, 1):
        print(f"{rank}. {source.source_id} {source.title} score={source.score:.6f}")
    ids, content = result.id_dedup_diagnostics, result.content_redundancy_diagnostics
    print(f"Raw={ids.raw_candidate_count}; unique={ids.unique_source_count}; "
          f"within_branch_removed={ids.within_branch_duplicate_count}; shared_ids={ids.shared_source_ids}")
    print(f"Duplicate content groups={content.duplicate_content_group_count}; "
          f"extra_sources={content.duplicate_content_extra_count}; "
          f"overlapping_adjacent_pairs={content.overlapping_adjacent_pair_count}; "
          f"coordinate_issues={len(content.coordinate_issues)}")
    print(f"Inputs unchanged: {inputs_unchanged}")
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
