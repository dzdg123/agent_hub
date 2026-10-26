"""R01～R15 固定规则验收；端到端层只测试 R01～R05 的检索连接，不测真实模型质量。"""

from copy import deepcopy
import json
import re

import pytest
import respx

from day10_support import CASES, MANIFEST, RUNS, execute_case, run_id
from research_agent.models import ModelReply
from research_agent.rag import generate_answer
from research_agent.rag_render import audit_reference_locations, render_answer_markdown, render_answer_preview
from research_agent.rag_review import can_publish_answer


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    from research_agent.embeddings import SentenceTransformerEmbedder

    def forbidden(*args, **kwargs):
        pytest.fail("Day10 固定验收禁止加载真实 Embedding 模型")
    monkeypatch.setattr(SentenceTransformerEmbedder, "__init__", forbidden)
    # 未声明的 HTTP 请求直接失败，包括任何意外真实 DeepSeek/搜索请求。
    with respx.mock(assert_all_called=False) as router:
        yield router


def test_case_contract_is_complete_before_execution():
    assert [case["case_id"] for case in CASES] == [f"R{index:02}" for index in range(1, 16)]
    assert len({run_id(case) for case in RUNS}) == len(RUNS)
    required = {"case_id", "scenario", "question", "source_keys", "retrieval_config",
                "expected", "necessary_evidence", "forbidden_assertions", "mock_script"}
    for case in RUNS:
        assert required <= case.keys()
        assert case["question"].strip()
        assert set(case["source_keys"]) <= MANIFEST["sources"].keys()
        assert 0 <= case["expected"]["requests"] <= 2
        for ref in case["necessary_evidence"]:
            assert ref["source_key"] in case["source_keys"]
            assert ref["quote"] in MANIFEST["sources"][ref["source_key"]]["content"]
    web = MANIFEST["sources"]["web_result"]
    assert web["metadata"]["provenance"] == "synthetic"
    assert web["metadata"]["network_fetched_at"] is None
    assert web["metadata"]["search_snippet"] not in web["content"]


def assert_run(case, bundle, root):
    expected = case["expected"]
    result, reviewed, scope = bundle["result"], bundle["reviewed"], bundle["scope"]
    assert result.status == expected["result_status"]
    assert result.structural_validation == expected["structural_validation"]
    assert result.source_validation == expected["source_validation"]
    assert result.support_review == expected["support_review"]
    assert (result.draft.status if result.draft else None) == expected["draft_status"]
    assert bundle["generation_requests"] == expected["requests"]
    assert len(result.attempts) <= 2
    if hasattr(bundle["model"], "calls"):
        assert len(bundle["model"].calls) == expected["requests"]
        assert bundle["model"].response_formats == [{"type": "json_object"}] * expected["requests"]
        # 修复使用原上下文和原允许 ID；不能靠扩大范围修复。
        for messages in bundle["model"].calls:
            payload = json.loads(messages[1]["content"])
            assert payload["allowed_source_ids"] == [source.source_id for source in scope.visible_sources]
            assert payload["context"] == scope.context_result.text
        if expected["requests"] == 2:
            repair = json.loads(bundle["model"].calls[1][-1]["content"])
            assert repair["allowed_source_ids"] == [source.source_id for source in scope.visible_sources]
    if expected.get("issue_code"):
        assert all(expected["issue_code"] in [issue.code for issue in attempt.issues] for attempt in result.attempts)
    if expected.get("first_issue_code"):
        assert result.attempts[0].issues[0].code == expected["first_issue_code"]
        assert result.attempts[1].issues == []
    if expected.get("http_attempts"):
        assert bundle["http_attempts"] == expected["http_attempts"]
        assert result.attempts[-1].http_attempts == expected["http_attempts"]
        assert result.draft is None
        assert "用量" in result.message

    if "included_keys" in expected:
        assert scope.context_result.included_source_ids == [bundle["by_key"][key].source_id for key in expected["included_keys"]]
        assert scope.context_result.omitted_source_ids == [bundle["by_key"][key].source_id for key in expected["omitted_keys"]]

    # 用量包括坏 JSON/坏引用的回复；网络无回复时只记录已知部分。
    known_tokens = sum(attempt.reply.usage.total_tokens for attempt in result.attempts if attempt.reply)
    assert result.usage.total_tokens == known_tokens
    assert result.usage.model_calls == sum(attempt.reply is not None for attempt in result.attempts)
    markdown = None
    if result.draft is not None:
        for ref in case["necessary_evidence"]:
            evidence = result.draft.claims[ref["claim_index"]].evidence
            assert any(item.source_id == bundle["by_key"][ref["source_key"]].source_id
                       and item.quote == ref["quote"] for item in evidence)
        text = "\n".join([claim.text for claim in result.draft.claims] + result.draft.limitations)
        forbidden_hits = [value for value in case["forbidden_assertions"] if value in text]
        if case["case_id"] == "R13":
            assert forbidden_hits, "R13 必须真的包含反转含义的错误，不能把夹具改成正确回答"
            assert reviewed.support_review == "failed"
            assert not can_publish_answer(reviewed, scope.visible_sources)
            with pytest.raises(ValueError):
                render_answer_markdown(reviewed, scope.visible_sources)
            with pytest.raises(ValueError):
                render_answer_preview(reviewed, scope.visible_sources)
        else:
            assert forbidden_hits == []
            assert not can_publish_answer(result, scope.visible_sources)  # 原始结果仍待审。
            if case.get("review"):
                assert reviewed.support_review == "passed"
                markdown = render_answer_markdown(reviewed, scope.visible_sources, base_dir=root)
                assert audit_reference_locations(reviewed, scope.visible_sources, base_dir=root) == []
                assert markdown == render_answer_markdown(reviewed, scope.visible_sources, base_dir=root)
                cited = {ref.source_id for claim in result.draft.claims for ref in claim.evidence}
                anchors = re.findall(r'<a id="(ref-\d+)"></a>', markdown)
                assert len(anchors) == len(cited)
                assert set(re.findall(r"\]\(#(ref-\d+)\)", markdown)) == set(anchors)
    else:
        assert not can_publish_answer(result, scope.visible_sources)
        with pytest.raises(ValueError):
            render_answer_markdown(result, scope.visible_sources)
        with pytest.raises(ValueError):
            render_answer_preview(result, scope.visible_sources)
    return markdown


def record_run(record_property, case, layer, bundle, markdown):
    record_property("case_id", case["case_id"])
    record_property("variant_id", case["variant_id"])
    record_property("layer", layer)
    record_property("evaluation_kind", "mock_rule_test")
    record_property("diagnostics", json.dumps({
        "real_model_calls": 0, "fixture_review_only": True,
        "provenance": MANIFEST["provenance"], "fixture_timestamp": MANIFEST["fixture_timestamp"],
        "question": case["question"], "expected": case["expected"],
        "allowed_ids": [source.source_id for source in bundle["scope"].visible_sources],
        "context": bundle["scope"].context_result.text if bundle["scope"].context_result else None,
        "retrieval": bundle["retrieval"], "mocked_http_attempts": bundle["http_attempts"],
        "result": bundle["reviewed"].model_dump(mode="json"), "markdown": markdown,
    }, ensure_ascii=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", RUNS, ids=run_id)
async def test_fixed_evidence_cases(case, tmp_path, scripted_model, offline_only, monkeypatch, record_property):
    bundle = await execute_case(case, "fixed", tmp_path / "corpus", scripted_model, offline_only, monkeypatch)
    markdown = assert_run(case, bundle, tmp_path / "corpus")
    if case["case_id"] in {"R02", "R05"}:
        # 每条说法的正文位置都有引用，不能只在参考资料区放一个编号。
        claim_lines = [line for line in markdown.splitlines() if line.startswith("- ") and "](#ref-" in line]
        assert len(claim_lines) == 2
    if case["case_id"] == "R03":
        assert bundle["result"].resolved_evidence[0].page == 2
        assert "物理页：2" in markdown and "#page=2" in markdown
    if case["case_id"] == "R04":
        assert case["expected"]["reference_url"] in markdown
        assert "99" not in markdown
    record_run(record_property, case, "fixed", bundle, markdown)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES[:5], ids=lambda case: case["case_id"])
async def test_end_to_end_retrieval_cases(case, tmp_path, scripted_model, offline_only, monkeypatch, record_property):
    case = deepcopy(case)
    case["variant_id"] = "base"
    bundle = await execute_case(case, "e2e", tmp_path / "corpus", scripted_model, offline_only, monkeypatch)
    assert bundle["retrieval"]["engine"] == "KeywordIndex"
    assert all(score > 0 for score in bundle["retrieval"]["scores"])
    assert "doc-unrelated" not in bundle["scope"].context_result.included_source_ids
    for item in case["necessary_evidence"]:
        assert bundle["by_key"][item["source_key"]].source_id in bundle["scope"].context_result.included_source_ids
    markdown = assert_run(case, bundle, tmp_path / "corpus")
    if case["case_id"] == "R03":
        source = bundle["by_key"]["pdf_steps"]
        assert source.page == 2 and source.metadata["empty_pages"] == [1]
        assert "物理页：2" in markdown
    record_run(record_property, case, "e2e", bundle, markdown)


@pytest.mark.asyncio
async def test_r04_search_snippet_cannot_replace_web_body(tmp_path, scripted_model, offline_only, monkeypatch):
    case = deepcopy(CASES[3])
    case["variant_id"] = "snippet_is_not_body"
    entry = case["mock_script"][0]
    entry["repeat"] = 2
    entry["value"]["claims"][0]["evidence"][0]["quote"] = MANIFEST["sources"]["web_result"]["metadata"]["search_snippet"]
    bundle = await execute_case(case, "fixed", tmp_path, scripted_model, offline_only, monkeypatch)
    assert bundle["result"].status == "validation_failed"
    assert all(attempt.issues[0].code == "quote_not_found" for attempt in bundle["result"].attempts)


@pytest.mark.asyncio
async def test_r15_first_bad_reply_usage_survives_later_transport_failure(
    tmp_path, scripted_model, offline_only, monkeypatch,
):
    from research_agent.llm import LLMError

    case = deepcopy(RUNS[0])
    bundle = await execute_case(case, "fixed", tmp_path, scripted_model, offline_only, monkeypatch)
    model = scripted_model([
        ModelReply(content="bad", usage=bundle["result"].usage.model_copy(deep=True)),
        LLMError("offline transport error", http_attempts=3),
    ])
    result = await generate_answer(model, case["question"], bundle["scope"])
    assert result.status == "model_failed"
    assert result.usage.total_tokens == 15
    assert len(result.attempts) == 2
    assert result.attempts[1].http_attempts == 3
