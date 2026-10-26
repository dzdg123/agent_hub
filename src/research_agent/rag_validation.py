"""结构/来源两层验证及摘录定位；不判断说法是否受证据支持。"""

import hashlib
import json
import re

from pydantic import ValidationError

from .models import Source
from .rag_models import (
    AnswerDraft, DraftValidationReport, QuoteOccurrence, ResolvedEvidence, ValidationIssue,
)


def build_canonical_source_map(sources: list[Source]) -> dict[str, Source]:
    by_id: dict[str, Source] = {}
    for source in sources:
        if not source.source_id.strip():
            raise ValueError("规范来源 ID 不能为空")
        if source.source_id in by_id:
            raise ValueError(f"规范来源中存在重复 ID：{source.source_id}")
        if "_retrieval" in source.metadata:
            raise ValueError("规范来源不能包含运行时 _retrieval 数据")
        by_id[source.source_id] = source
    return by_id


def schema_issues(exc: ValidationError) -> list[ValidationIssue]:
    issues = []
    for error in exc.errors(include_input=False, include_context=False):
        path = "draft"
        for part in error["loc"]:
            path += f"[{part}]" if isinstance(part, int) else f".{part}"
        issues.append(ValidationIssue(code=error["type"], path=path, message=error["msg"]))
    return issues


def validate_draft_structure(draft: AnswerDraft) -> list[ValidationIssue]:
    issues = []
    if draft.status in {"answered", "partial"} and not draft.claims:
        issues.append(ValidationIssue(
            code="claims_required", path="claims", message=f"{draft.status} 至少需要一条说法",
        ))
    if draft.status in {"partial", "insufficient_evidence"} and not draft.limitations:
        issues.append(ValidationIssue(
            code="limitations_required", path="limitations",
            message=f"{draft.status} 需要说明当前资料的缺口",
        ))
    if draft.status == "insufficient_evidence" and draft.claims:
        issues.append(ValidationIssue(
            code="claims_not_allowed", path="claims",
            message="insufficient_evidence 的 claims 必须为空",
        ))
    # 短答的自由字段只作为纯文本；引用只能来自 evidence。
    # 对未知 ID 也拒绝，不能只检测已知的 doc-/web- 前缀。
    forbidden = re.compile(
        r"\[[^\]\r\n]*\]|〔[^〕\r\n]*〕|【[^】\r\n]*】"
        r"|</?[A-Za-z][^>]*>|<!--"
        r"|(?:https?://|www\.|javascript:|data:|file:|mailto:)",
        re.IGNORECASE,
    )
    fields = [(f"claims[{index}].text", claim.text) for index, claim in enumerate(draft.claims)]
    fields.extend((f"limitations[{index}]", text) for index, text in enumerate(draft.limitations))
    for path, text in fields:
        if forbidden.search(text):
            issues.append(ValidationIssue(
                code="free_text_markup", path=path,
                message="请使用纯文本，不得手写引用、链接或 HTML；引用仅由 evidence 提供",
            ))
    return issues


def _normalized_basis(source: Source) -> str | None:
    start = source.metadata.get("offset")
    end = source.metadata.get("end_offset")
    basis = source.metadata.get("offset_basis")
    expected_basis = "normalized_page_text" if source.page is not None else "normalized_document_text"
    if (
        type(start) is int and type(end) is int and 0 <= start <= end
        and end - start == len(source.content) and basis == expected_basis
    ):
        return basis
    return None


def locate_quote(source: Source, quote: str) -> list[QuoteOccurrence]:
    """记录所有精确匹配，包括重叠出现；不删除空白、不做模糊匹配。"""
    if not quote.strip():
        raise ValueError("摘录不能为空白")
    basis = _normalized_basis(source)
    positions = []
    cursor = 0
    while (start := source.content.find(quote, cursor)) != -1:
        end = start + len(quote)
        offset = source.metadata["offset"] if basis is not None else None
        positions.append(QuoteOccurrence(
            local_start=start, local_end=end,
            normalized_start=offset + start if offset is not None else None,
            normalized_end=offset + end if offset is not None else None,
        ))
        cursor = start + 1
    return positions


def validate_draft_layers(draft: AnswerDraft, visible_sources: list[Source]) -> DraftValidationReport:
    # 防止调用方在 Pydantic 构造后直接修改字段而绕过 Schema。
    try:
        checked = AnswerDraft.model_validate(draft.model_dump())
    except ValidationError as exc:
        return DraftValidationReport(structural_validation="failed", issues=schema_issues(exc))
    issues = validate_draft_structure(checked)
    if issues:
        return DraftValidationReport(structural_validation="failed", issues=issues)

    report = DraftValidationReport(structural_validation="passed")
    try:
        by_id = build_canonical_source_map(visible_sources)
    except ValueError as exc:
        report.source_validation = "failed"
        report.issues.append(ValidationIssue(
            code="invalid_canonical_sources", path="visible_sources", message=str(exc),
        ))
        return report

    for claim_index, claim in enumerate(checked.claims):
        for evidence_index, ref in enumerate(claim.evidence):
            path = f"claims[{claim_index}].evidence[{evidence_index}]"
            source = by_id.get(ref.source_id)
            if source is None:
                report.issues.append(ValidationIssue(
                    code="source_not_visible", path=f"{path}.source_id",
                    message=f"{ref.source_id!r} 不在本次允许引用的来源表中",
                ))
                continue
            if source.page is not None and source.page < 1:
                report.issues.append(ValidationIssue(
                    code="invalid_source_location", path=f"{path}.source_id",
                    message="规范来源的物理页码必须为正整数",
                ))
                continue
            occurrences = locate_quote(source, ref.quote)
            if not occurrences:
                report.issues.append(ValidationIssue(
                    code="quote_not_found", path=f"{path}.quote",
                    message=f"摘录不是来源 {ref.source_id!r} 中连续且准确的原文",
                ))
                continue
            report.resolved_evidence.append(ResolvedEvidence(
                claim_index=claim_index, evidence_index=evidence_index,
                source_id=source.source_id, quote=ref.quote, title=source.title,
                file_path=source.file_path, url=source.url, page=source.page,
                offset_basis=_normalized_basis(source), occurrences=occurrences,
            ))

    report.source_validation = "failed" if report.issues else "passed"
    # 部分来源有效也不能作为一份整体通过的引用表交给渲染器。
    if report.issues:
        report.resolved_evidence = []
    return report


def review_fingerprint(question: str, draft: AnswerDraft, sources: list[Source]) -> str:
    """绑定问题、草稿及规范来源，防止把旧审核复用到已修改的内容。"""
    by_id = build_canonical_source_map(sources)
    payload = {
        "question": question,
        "draft": draft.model_dump(mode="json"),
        "sources": [
            by_id[source_id].model_dump(mode="json", exclude={"score", "fetched_at"})
            for source_id in sorted(by_id)
        ],
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
