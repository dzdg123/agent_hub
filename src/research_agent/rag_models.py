from dataclasses import dataclass
from typing import Annotated, Literal

from datetime import datetime

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .context import ContextResult
from .models import ModelReply, Source, Usage, utc_now

PreparationStatus = Literal[
    "ready",
    "no_candidates",
    "no_allowed_sources",
    "budget_exhausted",
]

@dataclass
class EvidenceScope:
    status: PreparationStatus
    context_result: ContextResult | None
    visible_sources: list[Source]
    message: str | None = None


def _reject_blank(value: str) -> str:
    """仅检查空白，不改写 ID 和摘录，保证后续能精确比较。"""
    if not value.strip():
        raise ValueError("文本不能只包含空白")
    return value


SourceId = Annotated[
    str, Field(min_length=1, max_length=200), AfterValidator(_reject_blank)
]
QuoteText = Annotated[
    str, Field(min_length=1, max_length=1000), AfterValidator(_reject_blank)
]
ClaimText = Annotated[
    str, Field(min_length=1, max_length=1000), AfterValidator(_reject_blank)
]
LimitationText = Annotated[
    str, Field(min_length=1, max_length=500), AfterValidator(_reject_blank)
]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_id: SourceId
    quote: QuoteText


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: ClaimText
    kind: Literal["fact", "inference"]
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=5)

    @field_validator("evidence")
    @classmethod
    def deduplicate_evidence(cls, evidence: list[EvidenceRef]) -> list[EvidenceRef]:
        """同一说法内保留首次出现的 (source_id, quote)。"""
        seen: set[tuple[str, str]] = set()
        result: list[EvidenceRef] = []
        for ref in evidence:
            key = (ref.source_id, ref.quote)
            if key not in seen:
                seen.add(key)
                result.append(ref)
        return result


class AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["answered", "partial", "insufficient_evidence"]
    claims: list[Claim] = Field(max_length=5)
    limitations: list[LimitationText] = Field(max_length=5)


class ValidationIssue(BaseModel):
    """业务校验问题；path 是字段定位字符串，不是文件路径。"""
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str
    path: str
    message: str


LayerStatus = Literal["passed", "failed", "not_run"]


class QuoteOccurrence(BaseModel):
    """全部坐标均为 Python 字符数的左闭右开区间，不是原文件字节位置。"""
    model_config = ConfigDict(extra="forbid", strict=True)

    local_start: int = Field(ge=0)
    local_end: int = Field(gt=0)
    normalized_start: int | None = None
    normalized_end: int | None = None


class ResolvedEvidence(BaseModel):
    """由规范 Source 生成的位置记录，模型不能提交这些字段。"""
    model_config = ConfigDict(extra="forbid", strict=True)

    claim_index: int
    evidence_index: int
    source_id: str
    quote: str
    title: str
    file_path: str | None
    url: str | None
    page: int | None
    offset_basis: Literal["normalized_page_text", "normalized_document_text"] | None
    occurrences: list[QuoteOccurrence]


class DraftValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structural_validation: LayerStatus = "not_run"
    source_validation: LayerStatus = "not_run"
    issues: list[ValidationIssue] = Field(default_factory=list)
    resolved_evidence: list[ResolvedEvidence] = Field(default_factory=list)


ReviewCheckStatus = Literal["passed", "failed", "not_applicable"]


class SupportChecks(BaseModel):
    """审核者逐项判断；程序不能根据摘录匹配自动填写这些结论。"""
    model_config = ConfigDict(extra="forbid", strict=True)

    directly_supported: ReviewCheckStatus
    numbers_units_time_subject: ReviewCheckStatus
    scope_not_expanded: ReviewCheckStatus
    inference_labeled: ReviewCheckStatus
    conflicts_not_hidden: ReviewCheckStatus
    question_addressed: ReviewCheckStatus


class SupportReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    draft_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: Literal["answer", "claim", "limitation"]
    index: int | None = Field(default=None, ge=0)
    reviewer: Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_reject_blank)]
    review_method: Literal["human", "ai_assisted"]
    verdict: Literal["passed", "failed"]
    reason: Annotated[str, Field(min_length=1, max_length=2000), AfterValidator(_reject_blank)]
    checks: SupportChecks
    reviewed_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def check_review_consistency(self) -> "SupportReviewRecord":
        if (self.target == "answer") != (self.index is None):
            raise ValueError("answer 不使用 index；claim/limitation 必须提供 index")
        values = self.checks.model_dump().values()
        if all(value == "not_applicable" for value in values):
            raise ValueError("不能把所有审核维度都标记为不适用")
        expected = "failed" if "failed" in values else "passed"
        if self.verdict != expected:
            raise ValueError("verdict 必须与逐项审核结果一致")
        return self


class DraftAttempt(BaseModel):
    """一次生成或修复的诊断；原始回复不作为正常答案发布。"""
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1, le=2)
    reply: ModelReply | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    error: str | None = None
    http_attempts: int | None = Field(default=None, ge=1)
    elapsed_seconds: float = Field(default=0, ge=0)
    validation: DraftValidationReport | None = None


class AnswerResult(BaseModel):
    """程序校验结果；program_validated 仍需要后续事实支持性审核。"""
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "program_validated", "no_candidates", "no_allowed_sources",
        "budget_exhausted", "validation_failed", "model_failed",
    ]
    draft: AnswerDraft | None = None
    usage: Usage = Field(default_factory=Usage)
    attempts: list[DraftAttempt] = Field(default_factory=list)
    message: str | None = None
    question: str | None = None
    structural_validation: LayerStatus = "not_run"
    source_validation: LayerStatus = "not_run"
    support_review: Literal["pending", "passed", "failed"] = "pending"
    resolved_evidence: list[ResolvedEvidence] = Field(default_factory=list)
    review_fingerprint: str | None = None
    reviews: list[SupportReviewRecord] = Field(default_factory=list)
