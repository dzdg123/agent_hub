"""阶段五离线演示：真实摘录可通过程序检查，但相反结论仍待内容审核。

审核记录在本脚本中预先填写，仅展示接口，不是自动识别语义错误的算法。
不调用真实 API，不产生模型费用。
"""

import asyncio
import json

from research_agent.models import ModelReply, Source
from research_agent.rag import generate_answer, prepare_evidence_scope
from research_agent.rag_models import SupportChecks, SupportReviewRecord
from research_agent.rag_review import apply_support_reviews, can_publish_answer


class FixedReplyModel:
    async def complete(self, messages, *, tools=None, response_format=None, max_tokens=None):
        return ModelReply(content=json.dumps({
            "status": "answered",
            "claims": [{
                "text": "实验已证明收益增长。", "kind": "fact",
                "evidence": [{
                    "source_id": "doc-experiment", "quote": "实验未证明收益增长。",
                }],
            }],
            "limitations": [],
        }, ensure_ascii=False))


async def main():
    content = "实验未证明收益增长。"
    source = Source(
        source_id="doc-experiment", title="固定合成资料", content=content,
        metadata={"offset": 100, "end_offset": 100 + len(content),
                  "offset_basis": "normalized_document_text"},
    )
    scope = prepare_evidence_scope([source], [source])
    result = await generate_answer(FixedReplyModel(), "实验是否证明收益增长？", scope)

    # 这是针对已知固定例子预先填写的演示判断，不声称已完成真人审核。
    review = SupportReviewRecord(
        draft_fingerprint=result.review_fingerprint,
        target="claim", index=0,
        reviewer="固定 AI 辅助示例（非人工验收）", review_method="ai_assisted",
        verdict="failed",
        reason="原文说未证明，说法改成已证明，否定关系被反转。",
        checks=SupportChecks(
            directly_supported="failed", numbers_units_time_subject="passed",
            scope_not_expanded="passed", inference_labeled="not_applicable",
            conflicts_not_hidden="not_applicable", question_addressed="passed",
        ),
    )
    reviewed = apply_support_reviews(result, scope.visible_sources, [review])
    print(json.dumps({
        "sample_review_only": True,
        "note": "审核结论预先填写；程序不会自动判断这条说法的语义。",
        "before_review": {
            "structural_validation": result.structural_validation,
            "source_validation": result.source_validation,
            "support_review": result.support_review,
            "can_publish": can_publish_answer(result, scope.visible_sources),
        },
        "after_review": reviewed.model_dump(mode="json"),
        "can_publish": can_publish_answer(reviewed, scope.visible_sources),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
