"""阶段七：受控故障演示，不加载真实模型；降级结果单独统计。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from research_agent.context import build_context
from research_agent.models import Source
from research_agent.retrieval import KeywordIndex
from research_agent.retrieval_errors import operational_boundary
from research_agent.retrieval_pipeline import LazyCandidateIndex, TwoBranchRetriever


class ControlledIndex(KeywordIndex):
    """用故障开关验证契约，不代表真实向量检索效果。"""

    def __init__(self, sources: list[Source], mode: str = "ok") -> None:
        super().__init__()
        self.add(sources)
        self.mode = mode

    def search(self, query, top_k=5, *, allowed_ids=None):
        if self.mode == "failed":
            with operational_boundary("受控分支查询"):
                raise TimeoutError("模拟超时")
        if self.mode == "empty":
            return []
        return super().search(query, top_k, allowed_ids=allowed_ids)


def run_demo() -> dict:
    sources = [Source(source_id="doc-offset", title="位置说明", content="offset 记录原文位置",
                      file_path="guide.txt", metadata={"file_type": "txt"})]
    cases = [
        ("both_ok", "ok", "ok", False),
        ("vector_empty", "ok", "empty", False),
        ("both_empty", "empty", "empty", False),
        ("vector_failure_strict", "ok", "failed", False),
        ("vector_failure_allowed", "ok", "failed", True),
        ("keyword_failure_allowed", "failed", "ok", True),
        ("failure_and_empty", "empty", "failed", True),
        ("both_failed", "failed", "failed", True),
        ("initialization_failure", "ok", "initialization_failed", True),
    ]
    records = []
    for case_id, keyword_mode, vector_mode, allow in cases:
        keyword = ControlledIndex(sources, keyword_mode)
        if vector_mode == "initialization_failed":
            def unavailable():
                with operational_boundary("受控模型初始化"):
                    raise OSError("模拟模型文件不可用")
            vector = LazyCandidateIndex(unavailable)
        else:
            vector = ControlledIndex(sources, vector_mode)
        result = TwoBranchRetriever(sources, keyword_index=keyword, vector_index=vector).search(
            "offset", allow_degraded=allow, query_id=case_id,
        )
        context = None if result.status == "failed" else asdict(build_context(result.final_sources))
        records.append({"case_id": case_id, "result": asdict(result), "context": context})
    counts = Counter(record["result"]["status"] for record in records)
    return {"mode": "controlled_failures_not_semantic_evaluation", "records": records,
            "status_counts": dict(counts),
            "full_dual_branch_query_ids": [record["case_id"] for record in records
                                            if record["result"]["status"] in {"ok", "empty"}],
            "degraded_query_ids": [record["case_id"] for record in records
                                    if record["result"]["status"] == "degraded"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=(
        Path(__file__).resolve().parents[1] / "data/day09/failures"
    ))
    args = parser.parse_args()
    payload = run_demo()
    run_dir = args.output_root / uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)
    path = run_dir / "failures.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False,
                               default=lambda value: value.model_dump(mode="json")) + "\n",
                    encoding="utf-8")
    for record in payload["records"]:
        result = record["result"]
        print(f"{record['case_id']}: {result['status']}; final_count={result['final_count']}")
    print(f"Status counts: {payload['status_counts']}\nSaved: {path}")


if __name__ == "__main__":
    main()
