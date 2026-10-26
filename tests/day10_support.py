"""Day10 测试夹具执行器；不向真实模型或网站发起请求。"""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import shutil
from unittest.mock import AsyncMock

import httpx

from research_agent.context import format_source_block, render_context
from research_agent.documents import load_document, normalize_document_text
from research_agent.llm import DeepSeekClient
from research_agent.config import Settings
from research_agent.models import ModelReply, Source, Usage
from research_agent.rag import generate_answer, prepare_evidence_scope
from research_agent.rag_models import SupportChecks, SupportReviewRecord
from research_agent.rag_review import apply_support_reviews
from research_agent.retrieval import KeywordIndex
from research_agent.source_filters import resolve_allowed_ids


FIXTURES = Path(__file__).parent / "fixtures" / "day10"
MANIFEST = json.loads((FIXTURES / "sources.json").read_text(encoding="utf-8"))
CASES = [json.loads(line) for line in (FIXTURES / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def expand_cases():
    runs = []
    for case in CASES:
        base = deepcopy(case)
        base.pop("variants", None)
        base["variant_id"] = "base"
        runs.append(base)
        for variant in case.get("variants", []):
            item = deepcopy(base)
            for key, value in variant.items():
                if key in {"expected", "retrieval_config"}:
                    item[key].update(deepcopy(value))
                else:
                    item[key] = deepcopy(value)
            if item["expected"]["result_status"] != "program_validated":
                item["expected"]["first_issue_code"] = None
            runs.append(item)
    return runs


RUNS = expand_cases()


def run_id(case):
    return f"{case['case_id']}-{case['variant_id']}"


def materialize_sources(case, root, *, load_files):
    root.mkdir(parents=True, exist_ok=True)
    by_key = {}
    for key in case["source_keys"]:
        spec = MANIFEST["sources"][key]
        filename = spec.get("file")
        if filename:
            path = root / filename
            if spec.get("pages"):
                import pymupdf

                with pymupdf.open() as document:
                    for text in spec["pages"]:
                        page = document.new_page()
                        if text:
                            page.insert_text((72, 72), text)
                    document.save(path)
            else:
                shutil.copyfile(FIXTURES / "corpus" / filename, path)
                assert normalize_document_text(path.read_text(encoding="utf-8")) == spec["content"]
            if load_files:
                loaded = load_document(path, root, chunk_size=900, overlap=120)
                assert len(loaded) == 1, "固定本地资料应该生成一个非空片段"
                assert loaded[0].content == spec["content"]
                by_key[key] = loaded[0]
                continue
        metadata = deepcopy(spec.get("metadata", {}))
        metadata.update({
            "provenance": "synthetic", "fixture_timestamp": MANIFEST["fixture_timestamp"],
            "offset": 0, "end_offset": len(spec["content"]),
            "offset_basis": "normalized_page_text" if spec.get("page") else "normalized_document_text",
        })
        if filename:
            metadata.update(file_type=spec["file_type"], relative_path=filename)
        if spec.get("pages"):
            metadata["empty_pages"] = [index for index, text in enumerate(spec["pages"], 1) if not text]
        by_key[key] = Source(
            source_id=spec["source_id"], title=spec["title"], content=spec["content"],
            file_path=str(root / filename) if filename else None,
            page=spec.get("page"), url=spec.get("url"), metadata=metadata,
            fetched_at=datetime.fromisoformat(MANIFEST["fixture_timestamp"].replace("Z", "+00:00")),
        )
    return by_key


def bind_source_ids(value, by_key):
    """只绑定预先声明的测试模板，绝不解析模型回复来创建规范来源。"""
    if isinstance(value, list):
        return [bind_source_ids(item, by_key) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "source_id" and isinstance(item, str) and item.startswith("@"):
                result[key] = by_key[item[1:]].source_id
            else:
                result[key] = bind_source_ids(item, by_key)
        return result
    return value


def scripted_replies(case, by_key):
    replies = []
    for entry in case["mock_script"]:
        if entry["kind"] == "transport":
            continue
        content = (
            json.dumps(bind_source_ids(entry["value"], by_key), ensure_ascii=False)
            if entry["kind"] == "draft" else entry["content"]
        )
        tokens = entry["tokens"]
        for _ in range(entry.get("repeat", 1)):
            replies.append(ModelReply(
                content=content, request_id=f"mock-{run_id(case)}-{len(replies) + 1}",
                finish_reason=entry.get("finish_reason", "stop"),
                usage=Usage(prompt_tokens=tokens - 5, completion_tokens=5,
                            total_tokens=tokens, model_calls=1),
            ))
    return replies


def fixture_reviews(result, annotation):
    """使用规格中的预期审核，不冒充运行时人工审核或通用语义检测。"""
    failed = annotation["verdict"] == "failed"
    targets = [("claim", 0)] if failed else [
        ("answer", None),
        *(("claim", index) for index in range(len(result.draft.claims))),
        *(("limitation", index) for index in range(len(result.draft.limitations))),
    ]
    return [SupportReviewRecord(
        draft_fingerprint=result.review_fingerprint, target=target, index=index,
        reviewer="Day10固定期望审核夹具（非真人验收）", review_method="ai_assisted",
        verdict=annotation["verdict"], reason=annotation["reason"],
        checks=SupportChecks(
            directly_supported="failed" if failed else "passed",
            numbers_units_time_subject="passed", scope_not_expanded="passed",
            inference_labeled="not_applicable", conflicts_not_hidden="passed",
            question_addressed="passed",
        ),
    ) for target, index in targets]


async def execute_case(case, layer, root, scripted_model, router, monkeypatch):
    by_key = materialize_sources(case, root, load_files=layer == "e2e")
    sources = list(by_key.values())
    config = case["retrieval_config"]
    filters = {key: set(values) for key, values in config.get("filters", {}).items()} or None
    retrieval = None
    if layer == "e2e":
        # 当前生产关键词实现，不用假向量索引冒充真实 Embedding 测试。
        distractor = Source(source_id="doc-unrelated", title="无关资料", content="Astronomical catalog only.")
        sources.append(distractor)
        index = KeywordIndex()
        index.add(sources)
        candidates = index.search(config["query"], top_k=config["top_k"],
                                  allowed_ids=resolve_allowed_ids(sources, filters))
        retrieval = {
            "engine": "KeywordIndex", "query": config["query"],
            "candidate_ids": [source.source_id for source in candidates],
            "scores": [source.score for source in candidates],
        }
    else:
        candidates = [by_key[key] for key in config.get("candidate_keys", case["source_keys"])]
    budget = config.get("max_context_chars", 4000)
    if config.get("budget_fit_keys") is not None:
        budget = len(render_context([format_source_block(by_key[key]) for key in config["budget_fit_keys"]]))
    scope = prepare_evidence_scope(sources, candidates, filters=filters, max_context_chars=budget)
    before = deepcopy(sources)
    transport = next((entry for entry in case["mock_script"] if entry["kind"] == "transport"), None)
    route = None
    if transport:
        monkeypatch.setattr("research_agent.llm.asyncio.sleep", AsyncMock())
        failure = (httpx.ReadTimeout("fixed R15 timeout") if transport["failure"] == "timeout"
                   else httpx.Response(429, json={"error": {"message": "fixed R15 rate limit"}}))
        route = router.post("https://deepseek.invalid/chat/completions")
        if isinstance(failure, Exception):
            route.mock(side_effect=failure)
        else:
            route.mock(return_value=failure)
        model = DeepSeekClient(Settings(
            _env_file=None, deepseek_api_key="offline-not-real", deepseek_model="day10-rule-test-only",
            deepseek_base_url="https://deepseek.invalid", request_timeout_seconds=0.1,
        ), retries=transport["retries"])
    else:
        model = scripted_model(scripted_replies(case, by_key))
    result = await generate_answer(model, case["question"], scope, max_tokens=1024)
    assert sources == before, "生成不能修改规范来源"
    reviewed = result
    if case.get("review") and result.status == "program_validated":
        reviewed = apply_support_reviews(result, scope.visible_sources, fixture_reviews(result, case["review"]))
    return {
        "by_key": by_key, "sources": sources, "scope": scope, "result": result,
        "reviewed": reviewed, "model": model, "retrieval": retrieval,
        "generation_requests": len(result.attempts),
        "http_attempts": route.call_count if route is not None else 0,
    }
