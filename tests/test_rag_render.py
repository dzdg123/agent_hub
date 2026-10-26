"""阶段六：确定性引用渲染、审核门控、文本边界和真实文件核验。"""

from copy import deepcopy
from pathlib import Path
import re

import pytest

from research_agent.models import Source
from research_agent.rag_models import AnswerDraft, AnswerResult, SupportChecks, SupportReviewRecord
from research_agent.rag_render import audit_reference_locations, render_answer_markdown, render_answer_preview
from research_agent.rag_review import apply_support_reviews
from research_agent.rag_validation import review_fingerprint, validate_draft_layers


def make_claim(source_id, *, kind="fact", text="实验有三个步骤。", quote="实验有三个步骤。"):
    return {"text": text, "kind": kind, "evidence": [{"source_id": source_id, "quote": quote}]}


def make_result(sources, claims=None, *, status="answered", limitations=None, question="实验有几个步骤？"):
    draft = AnswerDraft.model_validate({
        "status": status,
        "claims": claims if claims is not None else [make_claim(sources[0].source_id)],
        "limitations": limitations or [],
    })
    report = validate_draft_layers(draft, sources)
    assert report.issues == []
    return AnswerResult(
        status="program_validated", question=question, draft=draft,
        structural_validation="passed", source_validation="passed",
        resolved_evidence=report.resolved_evidence,
        review_fingerprint=review_fingerprint(question, draft, sources),
    )


def approve(result, sources):
    # 仅为确定性渲染测试提供固定审核记录，不用于真实模型的自动认证。
    targets = [("answer", None)]
    targets += [("claim", index) for index in range(len(result.draft.claims))]
    targets += [("limitation", index) for index in range(len(result.draft.limitations))]
    checks = SupportChecks(**{name: "passed" for name in SupportChecks.model_fields})
    reviews = [SupportReviewRecord(
        draft_fingerprint=result.review_fingerprint, target=target, index=index,
        reviewer="渲染测试审核者", review_method="human", verdict="passed",
        reason="固定测试数据，核对渲染行为。", checks=checks,
    ) for target, index in targets]
    return apply_support_reviews(result, sources, reviews)


@pytest.fixture
def sources():
    return [Source(source_id=f"doc-{name}", title=f"资料{name}", content="实验有三个步骤。")
            for name in ("a", "b", "unused")]


def test_anchors_follow_original_first_use_and_all_resolve(sources):
    # 即使先出现的 inference 被排到后面的章节，锚点仍由原始数据顺序决定。
    claims = [make_claim("doc-b", kind="inference"), make_claim("doc-a"), make_claim("doc-b")]
    result = approve(make_result(sources, claims), sources)
    markdown = render_answer_markdown(result, sources)
    assert "[doc\\-b](#ref-1)" in markdown
    assert "[doc\\-a](#ref-2)" in markdown
    used = re.findall(r"\]\(#(ref-\d+)\)", markdown)
    targets = re.findall(r'<a id="(ref-\d+)"></a>', markdown)
    assert set(used) == set(targets) == {"ref-1", "ref-2"}
    assert len(targets) == len(set(targets))
    references = markdown.split("## 参考资料")[1]
    assert references.index('id="ref-1"') < references.index('id="ref-2"')
    assert "doc\\-unused" not in markdown
    assert "推断：" in markdown


def test_two_quotes_from_same_source_have_one_body_citation(sources):
    claim = make_claim("doc-a")
    claim["evidence"].append({"source_id": "doc-a", "quote": "三个步骤"})
    result = make_result(sources, [claim])
    markdown = render_answer_preview(result, sources)
    assert markdown.count("](#ref-1)") == 1
    assert markdown.count('<a id="ref-1"></a>') == 1


def test_formal_render_requires_actual_complete_review(sources):
    result = make_result(sources)
    with pytest.raises(ValueError, match="完整审核"):
        render_answer_markdown(result, sources)
    preview = render_answer_preview(result, sources)
    assert "草稿预览" in preview
    assert "待审核的事实说法" in preview
    assert "## 有证据支持的内容" not in preview
    result.support_review = "passed"
    with pytest.raises(ValueError):
        render_answer_markdown(result, sources)


def test_reviewed_failure_cannot_be_previewed(sources):
    result = make_result(sources)
    result.support_review = "failed"
    with pytest.raises(ValueError):
        render_answer_preview(result, sources)


def test_render_is_idempotent_and_does_not_modify_input(sources):
    result = approve(make_result(sources), sources)
    before = deepcopy(result)
    first = render_answer_markdown(result, sources)
    assert first == render_answer_markdown(result, sources)
    assert first.count("## 参考资料") == 1
    assert result == before


def test_special_source_ids_never_become_html_attributes():
    source = Source(source_id='odd"<tag>][id]', title='<img src=x onerror="bad"> *标题*', content="实验有三个步骤。")
    result = make_result([source])
    result.question = '<script>bad</script>\n# 新标题'
    result.review_fingerprint = review_fingerprint(result.question, result.draft, [source])
    markdown = render_answer_preview(result, [source])
    assert '<a id="ref-1"></a>' in markdown
    assert '<a id="odd' not in markdown
    assert "<script>" not in markdown
    assert "<img" not in markdown
    assert "&#10;" in markdown
    assert "\\[id\\]" in markdown


@pytest.mark.parametrize("value", [
    "javascript:alert(1)", "data:text/html,<script>bad</script>", "file:///C:/run.exe",
    "ftp://example.org/file", "https://bad.example\\@evil.example/", "https://bad.example/\nx",
])
def test_unsafe_urls_are_text_only(value):
    source = Source(source_id="doc-a", title="资料", content="实验有三个步骤。", url=value)
    markdown = render_answer_preview(make_result([source]), [source])
    assert "网址（仅文本）" in markdown
    assert "](<" not in markdown
    assert "<script>" not in markdown


def test_safe_url_special_characters_are_encoded():
    source = Source(source_id="doc-a", title="资料", content="实验有三个步骤。",
                    url='https://example.org/a b(x)?q="hello"#part(1)')
    markdown = render_answer_preview(make_result([source]), [source])
    assert '](<https://example.org/a%20b%28x%29?q=%22hello%22#part%281%29>)' in markdown


def test_pdf_fragments_have_separate_ids_text_pages_and_offsets(tmp_path):
    sources = [Source(
        source_id=f"doc-p{page}", title="同一 PDF", content="实验有三个步骤。",
        file_path="a b.pdf", page=page,
        metadata={"offset": 10, "end_offset": 19, "offset_basis": "normalized_page_text"},
    ) for page in (2, 3)]
    # 本测试只验证渲染，文件存在性由显式 audit 函数核对。
    for source in sources:
        source.metadata["end_offset"] = 10 + len(source.content)
    result = make_result(sources, [make_claim(source.source_id) for source in sources])
    markdown = render_answer_preview(result, sources, base_dir=tmp_path)
    assert "#page=2>)" in markdown and "#page=3>)" in markdown
    assert "物理页：2" in markdown and "物理页：3" in markdown
    assert "a%20b.pdf" in markdown
    assert markdown.count('<a id="ref-') == 2
    assert "规范化页文本" in markdown
    assert "不是原文件字节位置" in markdown


@pytest.mark.parametrize("status", ["partial", "insufficient_evidence"])
def test_partial_and_insufficient_evidence_do_not_claim_full_answer(sources, status):
    claims = [] if status == "insufficient_evidence" else [make_claim("doc-a")]
    result = make_result(sources, claims, status=status, limitations=["当前资料缺少对照结果。"])
    markdown = render_answer_preview(result, sources)
    assert "局限：当前资料缺少对照结果。" in markdown
    if not claims:
        assert "资料不足" in markdown
        assert "## 参考资料" not in markdown
        assert "事实说法" not in markdown
    else:
        assert "仅能回答部分问题" in markdown


@pytest.mark.parametrize("text", [
    "结论。[doc-a]", "结论。[unknown-id]", "结论。[^1]", "结论。〔doc-a〕",
    "结论。【web-fake】", "[点击](https://example.org)", "<b>结论</b>",
    "网址 https://example.org", "javascript:alert(1)",
])
def test_free_text_cannot_add_citations_or_links(sources, text):
    draft = AnswerDraft.model_validate({
        "status": "answered", "claims": [make_claim("doc-a", text=text)], "limitations": [],
    })
    report = validate_draft_layers(draft, sources)
    assert report.structural_validation == "failed"
    assert report.issues[0].code == "free_text_markup"
    assert report.issues[0].path == "claims[0].text"
    draft.claims[0].text = "普通说法。"
    draft.limitations = [text]
    assert validate_draft_layers(draft, sources).issues[0].path == "limitations[0]"


def test_quote_can_contain_literal_markup_but_never_creates_links():
    text = '原文有 [web-fake] 和 <script>bad</script>。'
    source = Source(source_id="doc-a", title="资料", content=text)
    result = make_result([source], [make_claim("doc-a", text="资料包含一段示例文字。", quote=text)])
    markdown = render_answer_preview(result, [source])
    assert "<script>" not in markdown
    assert "web-fake" not in markdown


def test_mutated_draft_source_or_resolved_locations_cannot_render(sources):
    original = make_result(sources)
    for field in ("draft", "source", "locations"):
        result, current_sources = deepcopy(original), deepcopy(sources)
        if field == "draft":
            result.draft.claims[0].text += "另一结论。"
        elif field == "source":
            current_sources[0].file_path = "changed.pdf"
        else:
            result.resolved_evidence[0].url = "https://different.example"
        with pytest.raises(ValueError):
            render_answer_preview(result, current_sources)


def test_audit_checks_actual_pdf_pages_and_ignores_uncited_missing_file(tmp_path):
    import pymupdf

    path = tmp_path / "actual.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.new_page()
        document.save(path)
    source = Source(source_id="doc-a", title="PDF", content="实验有三个步骤。", file_path="actual.pdf", page=2)
    unused = Source(source_id="doc-unused", title="未引用", content="其他资料", file_path="missing.pdf")
    sources = [source, unused]
    result = make_result(sources)
    assert audit_reference_locations(result, sources, base_dir=tmp_path) == []
    source.page = 3
    result = make_result(sources)
    issues = audit_reference_locations(result, sources, base_dir=tmp_path)
    assert [issue.code for issue in issues] == ["pdf_page_out_of_range"]


def test_audit_missing_and_unreadable_files(tmp_path):
    source = Source(source_id="doc-a", title="PDF", content="实验有三个步骤。", file_path="bad.pdf", page=1)
    result = make_result([source])
    assert audit_reference_locations(result, [source], base_dir=tmp_path)[0].code == "source_file_missing"
    (tmp_path / "bad.pdf").write_bytes(b"not a PDF")
    assert audit_reference_locations(result, [source], base_dir=tmp_path)[0].code == "pdf_unreadable"
