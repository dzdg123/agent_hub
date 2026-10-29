from __future__ import annotations

import json

import pytest

from research_agent.graph_state import create_research_graph_state
from research_agent.graph_workflow import (
    Day10AnswerService,
    ResearchGraphServices,
    build_research_graph,
)
from research_agent.models import ModelReply, Source, Usage
from research_agent.rag_models import AnswerResult


class FakeRetriever:
    def __init__(self, sources: list[Source] | None = None, error: Exception | None = None):
        self.sources = sources or []
        self.error = error
        self.calls: list[tuple[str, list[str], dict | None]] = []

    async def retrieve(self, query, plan, *, filters=None):
        self.calls.append((query, list(plan), filters))
        if self.error is not None:
            raise self.error
        return [source.model_copy(deep=True) for source in self.sources]


class JsonAnswerModel:
    def __init__(self, source: Source):
        self.source = source
        self.calls = []

    async def complete(
        self,
        messages,
        *,
        tools=None,
        response_format=None,
        max_tokens=None,
    ):
        self.calls.append(list(messages))
        assert response_format == {"type": "json_object"}
        return ModelReply(
            content=json.dumps(
                {
                    "status": "answered",
                    "claims": [
                        {
                            "text": "Agent 由模型、工具、状态和控制流程组成。",
                            "kind": "fact",
                            "evidence": [
                                {
                                    "source_id": self.source.source_id,
                                    "quote": self.source.content,
                                }
                            ],
                        }
                    ],
                    "limitations": [],
                },
                ensure_ascii=False,
            ),
            usage=Usage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                model_calls=1,
            ),
        )


class RecordingAnswerService:
    def __init__(self, result: AnswerResult | None = None):
        self.result = result
        self.calls = 0

    async def generate(self, question, scope):
        self.calls += 1
        if self.result is None:
            raise AssertionError("answer service must not be called")
        return self.result


@pytest.fixture
def source():
    return Source(
        source_id="doc-agent",
        title="Agent Notes",
        content="Agent 由模型、工具、状态和控制流程组成。",
        file_path="agent.md",
    )


@pytest.mark.asyncio
async def test_success_path_uses_five_nodes_and_creates_pending_preview(source):
    retriever = FakeRetriever([source])
    model = JsonAnswerModel(source)
    graph = build_research_graph(
        ResearchGraphServices(
            retriever=retriever,
            answer_service=Day10AnswerService(model),
            canonical_sources=(source,),
        )
    )

    result = await graph.ainvoke(
        create_research_graph_state("Agent 由什么组成？"),
        config={"recursion_limit": 20},
    )

    assert result["status"] == "awaiting_review"
    assert result["stop_reason"] is None
    assert result["plan"] == ["Agent 由什么组成？"]
    assert [item.source_id for item in result["candidates"]] == ["doc-agent"]
    assert result["evidence_scope"].status == "ready"
    assert result["answer_result"].status == "program_validated"
    assert "草稿预览" in result["report_preview"]
    assert result["usage"].total_tokens == 15
    assert result["usage"].model_calls == 1
    assert len(model.calls) == 1
    assert result["trace"] == [
        "plan:completed",
        "retrieve:found:1",
        "curate:ready:1",
        "write:program_validated",
        "validate:awaiting_review",
    ]


@pytest.mark.asyncio
async def test_no_candidates_skips_write_and_ends_with_reason(source):
    retriever = FakeRetriever([])
    answer_service = RecordingAnswerService()
    graph = build_research_graph(
        ResearchGraphServices(
            retriever=retriever,
            answer_service=answer_service,
            canonical_sources=(source,),
        )
    )

    result = await graph.ainvoke(
        create_research_graph_state("没有候选的问题"),
        config={"recursion_limit": 20},
    )

    assert result["status"] == "no_evidence"
    assert result["stop_reason"] == "no_candidates"
    assert result["answer_result"] is None
    assert result["report_preview"] is None
    assert result["usage"].model_calls == 0
    assert answer_service.calls == 0
    assert result["trace"] == [
        "plan:completed",
        "retrieve:found:0",
        "curate:no_candidates",
        "no_evidence:no_candidates",
    ]
    assert "未检索到" in result["errors"][0]


@pytest.mark.asyncio
async def test_retrieval_failure_routes_directly_to_end(source):
    retriever = FakeRetriever(error=RuntimeError("index unavailable"))
    answer_service = RecordingAnswerService()
    graph = build_research_graph(
        ResearchGraphServices(
            retriever=retriever,
            answer_service=answer_service,
            canonical_sources=(source,),
        )
    )

    result = await graph.ainvoke(
        create_research_graph_state("检索失败的问题"),
        config={"recursion_limit": 20},
    )

    assert result["status"] == "failed"
    assert result["stop_reason"] == "unexpected_error"
    assert result["trace"] == ["plan:completed", "retrieve:failed"]
    assert "index unavailable" in result["errors"][0]
    assert answer_service.calls == 0


@pytest.mark.asyncio
async def test_write_failure_counts_answer_result_usage_once(source):
    answer_service = RecordingAnswerService(
        AnswerResult(
            status="model_failed",
            question="问题",
            message="模型请求失败",
            usage=Usage(total_tokens=9, model_calls=1),
        )
    )
    graph = build_research_graph(
        ResearchGraphServices(
            retriever=FakeRetriever([source]),
            answer_service=answer_service,
            canonical_sources=(source,),
        )
    )
    initial = create_research_graph_state("问题")
    initial["usage"] = Usage(total_tokens=4, model_calls=1)

    result = await graph.ainvoke(initial, config={"recursion_limit": 20})

    assert result["status"] == "failed"
    assert result["stop_reason"] == "model_failed"
    assert result["usage"].total_tokens == 13
    assert result["usage"].model_calls == 2
    assert result["trace"][-1] == "write:model_failed"
    assert answer_service.calls == 1
