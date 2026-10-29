"""Day 11 stage-seven demo: inspect research graph state and Mermaid output.

The demo is fully offline.  It uses a deterministic retriever and model so
that invoking the graph several times does not access the network or incur
model cost.  ``--mode all`` intentionally executes the graph three times:
once for ``ainvoke``, once for update streaming and once for value streaming.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

from research_agent.graph_state import create_research_graph_state
from research_agent.graph_workflow import (
    Day10AnswerService,
    ResearchGraphServices,
    build_research_graph,
)
from research_agent.models import ModelReply, Source, Usage


DemoCase = Literal["evidence_available", "no_candidates", "retrieval_failure"]


SOURCE = Source(
    source_id="doc-agent",
    title="Agent Notes",
    content="Agent 由模型、工具、状态和控制流程组成。",
    file_path="data/demo/agent.md",
)

QUESTION = "Agent 由什么组成？"


class FakeRetriever:
    """Return a fixed candidate set or a fixed operational failure."""

    def __init__(self, case: DemoCase) -> None:
        self.case = case
        self.calls = 0

    async def retrieve(
        self,
        query: str,
        plan: list[str],
        *,
        filters: dict[str, set[str]] | None = None,
    ) -> list[Source]:
        self.calls += 1
        if self.case == "retrieval_failure":
            raise RuntimeError("演示用检索器不可用")
        if self.case == "no_candidates":
            return []
        return [SOURCE.model_copy(deep=True)]


class FakeAnswerModel:
    """Return one valid Day 10 structured answer without network access."""

    model_mode = "mock"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        messages,
        *,
        tools=None,
        response_format=None,
        max_tokens=None,
    ) -> ModelReply:
        self.calls += 1
        if response_format != {"type": "json_object"}:
            raise AssertionError("演示模型只接受 JSON 回答请求")

        payload = {
            "status": "answered",
            "claims": [
                {
                    "text": "Agent 由模型、工具、状态和控制流程组成。",
                    "kind": "fact",
                    "evidence": [
                        {
                            "source_id": SOURCE.source_id,
                            "quote": SOURCE.content,
                        }
                    ],
                }
            ],
            "limitations": [],
        }
        return ModelReply(
            content=json.dumps(payload, ensure_ascii=False),
            usage=Usage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                model_calls=1,
            ),
            request_id=f"fake-request-{self.calls}",
            finish_reason="stop",
            http_attempts=1,
        )


@dataclass
class DemoRuntime:
    graph: Any
    retriever: FakeRetriever
    model: FakeAnswerModel


def build_demo(case: DemoCase) -> DemoRuntime:
    retriever = FakeRetriever(case)
    model = FakeAnswerModel()
    services = ResearchGraphServices(
        retriever=retriever,
        answer_service=Day10AnswerService(model),
        canonical_sources=(SOURCE,),
        max_context_chars=2000,
    )
    return DemoRuntime(
        graph=build_research_graph(services),
        retriever=retriever,
        model=model,
    )


def make_initial(case: DemoCase, run_label: str):
    """Return a new dict and new mutable values for every invocation."""
    return create_research_graph_state(
        QUESTION,
        task_id=f"day11-{case}-{run_label}",
    )


def state_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Summarize a full state without dumping source or prompt contents."""
    scope = state.get("evidence_scope")
    answer = state.get("answer_result")
    usage = state["usage"]
    return {
        "task_id": state["task_id"],
        "query": state["query"],
        "status": state["status"],
        "stop_reason": state["stop_reason"],
        "plan_count": len(state["plan"]),
        "candidate_count": len(state["candidates"]),
        "evidence_status": scope.status if scope is not None else None,
        "visible_source_count": len(scope.visible_sources) if scope else 0,
        "answer_status": answer.status if answer is not None else None,
        "has_report_preview": state["report_preview"] is not None,
        "trace": list(state["trace"]),
        "errors": list(state["errors"]),
        "usage": {
            "model_calls": usage.model_calls,
            "total_tokens": usage.total_tokens,
            "estimated_cost": usage.estimated_cost,
        },
    }


def update_summary(node: str, update: dict[str, Any]) -> dict[str, Any]:
    """Summarize one node's partial update rather than treating it as state."""
    result: dict[str, Any] = {
        "node": node,
        "updated_fields": sorted(update),
    }
    for name in ("status", "stop_reason", "trace", "errors"):
        if name in update:
            result[name] = update[name]
    if "plan" in update:
        result["plan_count"] = len(update["plan"])
    if "candidates" in update:
        result["candidate_count"] = len(update["candidates"])
    if "evidence_scope" in update:
        scope = update["evidence_scope"]
        result["evidence_status"] = scope.status if scope is not None else None
        result["visible_source_count"] = (
            len(scope.visible_sources) if scope is not None else 0
        )
    if "answer_result" in update:
        answer = update["answer_result"]
        result["answer_status"] = answer.status if answer is not None else None
    if "report_preview" in update:
        result["has_report_preview"] = update["report_preview"] is not None
    if "usage" in update:
        usage = update["usage"]
        result["usage"] = {
            "model_calls": usage.model_calls,
            "total_tokens": usage.total_tokens,
        }
    return result


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


async def demo_ainvoke(runtime: DemoRuntime, case: DemoCase) -> None:
    print("\n=== ainvoke：最终完整状态摘要 ===")
    started = perf_counter()
    result = await runtime.graph.ainvoke(
        make_initial(case, "ainvoke"),
        config={"recursion_limit": 20},
    )
    print_json(state_summary(result))
    print(f"elapsed_ms={((perf_counter() - started) * 1000):.2f}")


async def demo_updates(runtime: DemoRuntime, case: DemoCase) -> None:
    print("\n=== astream(updates)：每个节点的局部更新 ===")
    started = perf_counter()
    async for event in runtime.graph.astream(
        make_initial(case, "updates"),
        config={"recursion_limit": 20},
        stream_mode="updates",
    ):
        elapsed_ms = (perf_counter() - started) * 1000
        for node, update in event.items():
            summary = update_summary(node, update)
            summary["elapsed_ms"] = round(elapsed_ms, 2)
            print_json(summary)


async def demo_values(runtime: DemoRuntime, case: DemoCase) -> None:
    print("\n=== astream(values)：每一步合并后的完整状态摘要 ===")
    started = perf_counter()
    final_state = None
    step = 0
    async for state in runtime.graph.astream(
        make_initial(case, "values"),
        config={"recursion_limit": 20},
        stream_mode="values",
    ):
        final_state = state
        summary = state_summary(state)
        summary["step"] = step
        summary["elapsed_ms"] = round((perf_counter() - started) * 1000, 2)
        print_json(summary)
        step += 1

    if final_state is None:
        raise RuntimeError("values 流没有产生状态")
    print("values 最后一份状态就是本次运行的最终状态。")


def print_mermaid(runtime: DemoRuntime) -> None:
    print("\n=== Mermaid 源码 ===")
    print(runtime.graph.get_graph().draw_mermaid())


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="离线观察 Day 11 五节点研究图的状态更新",
    )
    parser.add_argument(
        "--case",
        choices=("evidence_available", "no_candidates", "retrieval_failure"),
        default="evidence_available",
    )
    parser.add_argument(
        "--mode",
        choices=("ainvoke", "updates", "values", "mermaid", "all"),
        default="all",
    )
    args = parser.parse_args()

    case = args.case
    runtime = build_demo(case)
    print(f"case={case}, mode={args.mode}")
    print("本演示不访问网络，也不调用真实模型。")

    if args.mode in {"ainvoke", "all"}:
        await demo_ainvoke(runtime, case)
    if args.mode in {"updates", "all"}:
        await demo_updates(runtime, case)
    if args.mode in {"values", "all"}:
        await demo_values(runtime, case)
    if args.mode in {"mermaid", "all"}:
        print_mermaid(runtime)

    print(
        "\nservice_call_totals:",
        {
            "retriever_calls": runtime.retriever.calls,
            "model_calls": runtime.model.calls,
        },
    )
    if args.mode == "all":
        print("注意：all 模式执行了三次图，不是对同一次运行进行回放。")


if __name__ == "__main__":
    asyncio.run(main())
