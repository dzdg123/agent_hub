"""人工/明确标记 AI 辅助的内容审核记录；不自动调用 LLM Judge。"""

from .models import Source
from .rag_models import AnswerResult, SupportReviewRecord
from .rag_validation import review_fingerprint, validate_draft_layers


def _review_targets(result: AnswerResult) -> set[tuple[str, int | None]]:
    return {
        ("answer", None),
        *(("claim", index) for index in range(len(result.draft.claims))),
        *(("limitation", index) for index in range(len(result.draft.limitations))),
    }


def _check_reviewable(result: AnswerResult, visible_sources: list[Source]) -> None:
    if (
        result.status != "program_validated" or result.draft is None
        or result.structural_validation != "passed" or result.source_validation != "passed"
        or result.question is None
    ):
        raise ValueError("只有结构和来源层均通过的草稿才能进行内容审核")
    report = validate_draft_layers(result.draft, visible_sources)
    if report.structural_validation != "passed" or report.source_validation != "passed":
        raise ValueError("当前草稿或来源不再满足程序校验")
    fingerprint = review_fingerprint(result.question, result.draft, visible_sources)
    if result.review_fingerprint != fingerprint:
        raise ValueError("问题、草稿或规范来源已变化，请重新生成审核任务")


def _review_state(result: AnswerResult, records: list[SupportReviewRecord]) -> str:
    targets = _review_targets(result)
    seen = set()
    for record in records:
        # 不信任构造后被直接改写的 Pydantic 字段。
        record = SupportReviewRecord.model_validate(record.model_dump())
        if record.draft_fingerprint != result.review_fingerprint:
            raise ValueError("审核记录不属于当前问题、草稿和来源版本")
        target = (record.target, record.index)
        if target not in targets:
            raise ValueError(f"审核对象不存在：{target}")
        if record.target == "claim" and record.checks.directly_supported == "not_applicable":
            raise ValueError("说法审核必须检查证据支持关系")
        if record.target == "answer" and record.checks.question_addressed == "not_applicable":
            raise ValueError("整份回答审核必须检查是否回应原问题")
        if target in seen:
            raise ValueError(f"同一对象不能重复提交审核结论：{target}")
        seen.add(target)
    if any(record.verdict == "failed" for record in records):
        return "failed"
    return "passed" if seen == targets else "pending"


def apply_support_reviews(
    result: AnswerResult,
    visible_sources: list[Source],
    reviews: list[SupportReviewRecord],
) -> AnswerResult:
    """记录调用方提供的实际审核结论，返回副本，不改写原结果。

    必须覆盖整份回答（相关性与冲突）、每条说法和每条 limitation。
    不根据 quote 存在与否自动声称语义通过，也不认证 reviewer 的真实身份。
    """
    _check_reviewable(result, visible_sources)
    updated = result.model_copy(deep=True)
    records = [
        SupportReviewRecord.model_validate(record.model_dump())
        for record in [*updated.reviews, *reviews]
    ]
    updated.support_review = _review_state(updated, records)
    updated.reviews = records
    return updated


def can_publish_answer(result: AnswerResult, visible_sources: list[Source]) -> bool:
    """供后续渲染/发布入口使用：待审、失败或内容变化均不放行。"""
    try:
        _check_reviewable(result, visible_sources)
        if result.support_review != "passed" or _review_state(result, result.reviews) != "passed":
            return False
        # 定位信息也必须由本次规范来源生成，不能使用被改写的地址或页码。
        expected = validate_draft_layers(result.draft, visible_sources).resolved_evidence
        return result.resolved_evidence == expected
    except ValueError:
        return False
