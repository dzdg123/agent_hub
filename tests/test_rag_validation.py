"""阶段五：结构/来源定位与人工审核记录，全部离线。"""

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from research_agent.models import ModelReply, Source
from research_agent.rag import generate_answer, prepare_evidence_scope
from research_agent.rag_models import AnswerDraft, SupportChecks, SupportReviewRecord
from research_agent.rag_review import apply_support_reviews, can_publish_answer
from research_agent.rag_validation import locate_quote, validate_draft_layers


def draft_for(quote="实验未证明收益增长。", text="实验已证明收益增长。", limitations=None):
    return AnswerDraft.model_validate({
        "status": "answered",
        "claims": [{"text": text, "kind": "fact", "evidence": [
            {"source_id": "doc-a", "quote": quote},
        ]}],
        "limitations": [] if limitations is None else limitations,
    })


@pytest.fixture
def canonical():
    content = "实验未证明收益增长。"
    return Source(
        source_id="doc-a", title="实验结果", content=content,
        file_path="data/result.pdf", page=3, url="https://example.org/result",
        metadata={"offset": 100, "end_offset": 100 + len(content),
                  "offset_basis": "normalized_page_text"},
    )


def test_reversed_claim_passes_program_layers_but_is_not_semantic_proof(canonical):
    report = validate_draft_layers(draft_for(), [canonical])
    assert report.structural_validation == report.source_validation == "passed"
    assert report.issues == []
    location = report.resolved_evidence[0]
    assert location.file_path == canonical.file_path
    assert location.url == canonical.url
    assert location.page == 3
    assert location.offset_basis == "normalized_page_text"
    assert location.occurrences[0].local_start == 0
    assert location.occurrences[0].normalized_start == 100
    assert location.occurrences[0].normalized_end == 100 + len(canonical.content)


def test_quote_records_all_occurrences_including_overlaps():
    source = Source(source_id="doc-a", title="重复", content="哈哈哈")
    positions = locate_quote(source, "哈哈")
    assert [(item.local_start, item.local_end) for item in positions] == [(0, 2), (1, 3)]
    assert all(item.normalized_start is None for item in positions)


@pytest.mark.parametrize("metadata", [
    {},
    {"offset": True, "end_offset": 5, "offset_basis": "normalized_document_text"},
    {"offset": 10, "end_offset": 99, "offset_basis": "normalized_document_text"},
    {"offset": 10, "end_offset": 12, "offset_basis": "raw_file_bytes"},
    {"offset": 10, "end_offset": 12, "offset_basis": "normalized_page_text"},
])
def test_unreliable_offsets_only_expose_local_positions(metadata):
    source = Source(source_id="doc-a", title="坐标", content="中文", metadata=metadata)
    position = locate_quote(source, "文")[0]
    assert (position.local_start, position.local_end) == (1, 2)
    assert position.normalized_start is position.normalized_end is None


def test_document_offsets_count_characters_not_utf8_bytes():
    source = Source(source_id="doc-a", title="坐标", content="中文", metadata={
        "offset": 10, "end_offset": 12, "offset_basis": "normalized_document_text",
    })
    position = locate_quote(source, "文")[0]
    assert (position.normalized_start, position.normalized_end) == (11, 12)


def test_source_layer_rejects_duplicate_or_conflicting_id(canonical):
    conflict = canonical.model_copy(update={"content": "另一个正文"})
    for second in (canonical.model_copy(deep=True), conflict):
        report = validate_draft_layers(draft_for(), [canonical, second])
        assert report.structural_validation == "passed"
        assert report.source_validation == "failed"
        assert report.issues[0].code == "invalid_canonical_sources"
        assert report.resolved_evidence == []


@pytest.mark.parametrize("quote", ["实验已证明收益增长。", "实验收益增长", "实验未证明\n收益增长。"])
def test_source_layer_never_uses_fuzzy_match(canonical, quote):
    report = validate_draft_layers(draft_for(quote=quote), [canonical])
    assert report.structural_validation == "passed"
    assert report.source_validation == "failed"
    assert report.issues[0].code == "quote_not_found"


def test_source_page_must_be_positive(canonical):
    canonical.page = 0
    report = validate_draft_layers(draft_for(), [canonical])
    assert report.issues[0].code == "invalid_source_location"


def test_structure_rules_are_separate_and_revalidate_mutations(canonical):
    draft = draft_for()
    draft.claims = []
    report = validate_draft_layers(draft, [canonical])
    assert report.structural_validation == "failed"
    assert report.source_validation == "not_run"
    draft.claims = draft_for().claims
    draft.claims[0].text = " "
    assert validate_draft_layers(draft, [canonical]).structural_validation == "failed"


def test_model_cannot_supply_its_own_location_or_review():
    payload = draft_for().model_dump()
    payload["support_review"] = "passed"
    with pytest.raises(ValidationError):
        AnswerDraft.model_validate(payload)
    del payload["support_review"]
    payload["claims"][0]["evidence"][0]["file_path"] = "model-made-up.pdf"
    with pytest.raises(ValidationError):
        AnswerDraft.model_validate(payload)


async def generated_result(source, scripted_model, *, limitations=None, text="实验已证明收益增长。"):
    draft = draft_for(text=text, limitations=limitations)
    model = scripted_model([ModelReply(content=draft.model_dump_json())])
    scope = prepare_evidence_scope([source], [source])
    return await generate_answer(model, "实验是否证明收益增长？", scope)


def review_for(result, target, index=None, *, failed=False):
    # 固定测试数据，只测试记录接口；不是对真实模型的自动事实认证。
    checks = SupportChecks(
        directly_supported="failed" if failed else "passed",
        numbers_units_time_subject="passed", scope_not_expanded="passed",
        inference_labeled="not_applicable", conflicts_not_hidden="passed",
        question_addressed="passed",
    )
    return SupportReviewRecord(
        draft_fingerprint=result.review_fingerprint, target=target, index=index,
        reviewer="测试审核者", review_method="human",
        verdict="failed" if failed else "passed",
        reason="原文是否定结论，说法却是肯定结论。" if failed else "已逐项核对本测试的说法和原文。",
        checks=checks,
    )


@pytest.mark.asyncio
async def test_generation_defaults_to_pending_and_human_can_reject_semantics(canonical, scripted_model):
    result = await generated_result(canonical, scripted_model)
    assert result.structural_validation == result.source_validation == "passed"
    assert result.support_review == "pending"
    assert result.reviews == []
    assert not can_publish_answer(result, [canonical])
    rejected = apply_support_reviews(result, [canonical], [review_for(result, "claim", 0, failed=True)])
    assert rejected.support_review == "failed"
    assert rejected.reviews[0].reviewer == "测试审核者"
    assert rejected.reviews[0].reviewed_at is not None
    assert result.support_review == "pending"  # 返回副本，不修改原对象。
    assert not can_publish_answer(rejected, [canonical])


@pytest.mark.asyncio
async def test_review_covers_every_claim_limitation_and_whole_answer(canonical, scripted_model):
    result = await generated_result(
        canonical, scripted_model, text=canonical.content,
        limitations=["当前资料没有收益增长幅度的数据。"],
    )
    partial = apply_support_reviews(result, [canonical], [review_for(result, "claim", 0)])
    assert partial.support_review == "pending"
    partial = apply_support_reviews(partial, [canonical], [review_for(result, "answer")])
    assert partial.support_review == "pending"  # limitations 不是免审正文区。
    complete = apply_support_reviews(partial, [canonical], [review_for(result, "limitation", 0)])
    assert complete.support_review == "passed"
    assert can_publish_answer(complete, [canonical])
    assert complete.model_dump(mode="json")["reviews"][0]["review_method"] == "human"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["claim", "question", "quote", "source", "file_path", "page", "limitation"])
async def test_old_review_cannot_apply_after_content_changes(canonical, scripted_model, change):
    result = await generated_result(canonical, scripted_model)
    old = review_for(result, "claim", 0)
    if change == "claim":
        result.draft.claims[0].text = "不同说法"
    elif change == "question":
        result.question = "另一个问题"
    elif change == "quote":
        result.draft.claims[0].evidence[0].quote = "未证明"
    elif change == "source":
        canonical.content += "新的内容"
    elif change == "file_path":
        canonical.file_path = "different.pdf"
    elif change == "page":
        canonical.page = 4
    else:
        result.draft.limitations = ["增加的局限说明"]
    with pytest.raises(ValueError):
        apply_support_reviews(result, [canonical], [old])
    assert not can_publish_answer(result, [canonical])


@pytest.mark.asyncio
async def test_review_cannot_skip_checks_duplicate_targets_or_forge_flags(canonical, scripted_model):
    result = await generated_result(canonical, scripted_model, text=canonical.content)
    record = review_for(result, "claim", 0)
    invalid = record.model_copy(deep=True)
    invalid.checks.directly_supported = "failed"
    with pytest.raises(ValueError):
        apply_support_reviews(result, [canonical], [invalid])
    with pytest.raises(ValueError, match="重复"):
        apply_support_reviews(result, [canonical], [record, record])
    invalid = record.model_copy(deep=True)
    invalid.draft_fingerprint = "0" * 64
    with pytest.raises(ValueError, match="不属于"):
        apply_support_reviews(result, [canonical], [invalid])
    invalid = record.model_copy(deep=True)
    invalid.index = 999
    with pytest.raises(ValueError, match="不存在"):
        apply_support_reviews(result, [canonical], [invalid])
    result.support_review = "passed"
    assert not can_publish_answer(result, [canonical])  # 不能只改状态字段。


@pytest.mark.asyncio
async def test_location_tampering_blocks_publish(canonical, scripted_model):
    result = await generated_result(canonical, scripted_model, text=canonical.content)
    approved = apply_support_reviews(result, [canonical], [
        review_for(result, "claim", 0), review_for(result, "answer"),
    ])
    assert can_publish_answer(approved, [canonical])
    approved.resolved_evidence[0].url = "https://example.org/forged"
    assert not can_publish_answer(approved, [canonical])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure, structural, source", [
    ("bad_json", "failed", "not_run"),
    ("bad_source", "passed", "failed"),
])
async def test_failed_generation_exposes_independent_layer_statuses(
    canonical, scripted_model, failure, structural, source,
):
    draft = draft_for()
    draft.claims[0].evidence[0].source_id = "web-fake"
    raw = "not JSON" if failure == "bad_json" else draft.model_dump_json()
    model = scripted_model([ModelReply(content=raw), ModelReply(content=raw)])
    scope = prepare_evidence_scope([canonical], [canonical])
    result = await generate_answer(model, "问题", scope)
    assert result.status == "validation_failed"
    assert result.draft is None
    assert result.structural_validation == structural
    assert result.source_validation == source
    assert result.support_review == "pending"
    assert all(attempt.validation.structural_validation == structural for attempt in result.attempts)
