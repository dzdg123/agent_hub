from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from .citations import append_references, validate_citations
from .config import Settings
from .events import EventBroker
from .llm import ChatModel
from .models import Evidence, ResearchState, RunEvent, Source, Usage
from .retrieval import HybridIndex, merge_ranked
from .web import SearchProvider, fetch_webpage


class ResearchPlan(BaseModel):
    subqueries: list[str] = Field(min_length=1, max_length=5)


@dataclass
class ResearchServices:
    model: ChatModel
    index: HybridIndex
    search_provider: SearchProvider | None
    settings: Settings
    events: EventBroker


class ResearchWorkflow:
    def __init__(self, services: ResearchServices) -> None:
        self.services = services

    async def plan(self, task_id: str, query: str) -> list[str]:
        await self._event(task_id, "planning", "正在生成研究计划")
        reply = await self.services.model.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "把研究问题拆成最多五个互不重复的中文子问题。"
                        "只输出 JSON：{\"subqueries\":[\"...\"]}。简单问题只保留一个。"
                    ),
                },
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
        )
        try:
            plan = ResearchPlan.model_validate_json(reply.content)
            return plan.subqueries[: self.services.settings.max_subqueries]
        except Exception:
            return [query]

    async def run(
        self,
        *,
        task_id: str,
        query: str,
        plan: list[str],
        use_web: bool = True,
        use_documents: bool = True,
        is_cancelled=lambda: False,
    ) -> ResearchState:
        usage = Usage()
        errors: list[str] = []
        all_sources: dict[str, Source] = {}
        queries = plan or [query]

        for iteration in range(self.services.settings.max_research_iterations + 1):
            if is_cancelled():
                return self._state(task_id, query, plan, all_sources, usage, errors, iteration, "cancelled")
            await self._event(
                task_id,
                "retrieval",
                f"执行第 {iteration + 1} 轮检索",
                {"queries": queries},
            )
            semaphore = asyncio.Semaphore(self.services.settings.max_concurrency)

            async def limited(subquery: str) -> list[Source]:
                async with semaphore:
                    try:
                        return await self._retrieve(subquery, use_web, use_documents)
                    except Exception as exc:
                        errors.append(f"{subquery}: {type(exc).__name__}: {exc}")
                        return []

            result_sets = await asyncio.gather(*(limited(item) for item in queries))
            for source in merge_ranked(result_sets, top_k=20):
                all_sources[source.source_id] = source
            if len(all_sources) >= max(2, len(plan)) or iteration >= self.services.settings.max_research_iterations:
                break
            queries = [f"{query} 补充可靠事实、数据和不同观点"]

        if is_cancelled():
            return self._state(task_id, query, plan, all_sources, usage, errors, iteration, "cancelled")
        sources = list(all_sources.values())
        evidence = [
            Evidence(
                claim=f"与“{query}”相关的资料",
                excerpt=source.content[:500],
                source_id=source.source_id,
                relevance=max(0.0, min(source.score, 1.0)),
            )
            for source in sources
        ]
        await self._event(task_id, "writing", "正在根据证据生成报告", {"sources": len(sources)})
        report, report_usage = await self._write_report(query, plan, sources)
        usage.add(report_usage)
        invalid = validate_citations(report, sources)
        if invalid:
            errors.append(f"移除了不存在的引用: {', '.join(invalid)}")
            for source_id in invalid:
                report = report.replace(f"[{source_id}]", "[无效引用已移除]")
        report = append_references(report, sources)
        await self._event(task_id, "report_ready", "报告内容与引用校验已完成")
        return {
            "task_id": task_id,
            "query": query,
            "plan": plan,
            "sources": sources,
            "evidence": evidence,
            "report": report,
            "iteration": iteration,
            "status": "completed",
            "errors": errors,
            "usage": usage,
        }

    async def _retrieve(self, query: str, use_web: bool, use_documents: bool) -> list[Source]:
        result_sets: list[list[Source]] = []
        if use_documents:
            result_sets.append(self.services.index.search(query, top_k=5))
        if use_web and self.services.search_provider:
            search_results = await self.services.search_provider.search(query, max_results=5)
            pages = await asyncio.gather(
                *(fetch_webpage(item.url) for item in search_results[:2] if item.url),
                return_exceptions=True,
            )
            full_pages_by_id = {
                page.source_id: page
                for page in pages
                if isinstance(page, Source)
            }

            web_results = [
                full_pages_by_id.get(
                    search_result.source_id,
                    search_result,
                )
                for search_result in search_results
            ]

            result_sets.append(web_results)
        return merge_ranked(result_sets, top_k=8)

    async def _write_report(
        self, query: str, plan: list[str], sources: list[Source]
    ) -> tuple[str, Usage]:
        if not sources:
            return (
                f"# {query}\n\n现有检索没有提供足够证据，因此无法生成可靠结论。",
                Usage(),
            )
        context = "\n\n".join(
            f"[{source.source_id}] {source.title}\n{source.content[:2500]}" for source in sources[:12]
        )
        reply = await self.services.model.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的研究报告作者。只使用给定资料；每个可验证事实后使用资料中的"
                        "[source_id] 引用；不得创造来源编号。输出 Markdown，包含摘要、分析、局限和结论。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"研究问题：{query}\n研究计划：{json.dumps(plan, ensure_ascii=False)}\n资料：\n{context}",
                },
            ]
        )
        return reply.content, reply.usage

    async def _event(self, run_id: str, kind: str, message: str, data: dict | None = None) -> None:
        await self.services.events.publish(
            RunEvent(run_id=run_id, kind=kind, message=message, data=data or {})
        )

    @staticmethod
    def _state(task_id, query, plan, sources, usage, errors, iteration, status) -> ResearchState:
        return {
            "task_id": task_id,
            "query": query,
            "plan": plan,
            "sources": list(sources.values()),
            "evidence": [],
            "report": None,
            "iteration": iteration,
            "status": status,
            "errors": errors,
            "usage": usage,
        }


def build_langgraph(services: ResearchServices):
    """Build the same high-level flow as an inspectable LangGraph graph.

    The API uses an approval boundary before invoking the graph. This function is
    kept small so learners can compare a state graph with ``ResearchWorkflow``.
    """
    from langgraph.graph import END, START, StateGraph

    workflow = ResearchWorkflow(services)

    async def retrieve_and_write(state: ResearchState) -> ResearchState:
        return await workflow.run(
            task_id=state["task_id"],
            query=state["query"],
            plan=state.get("plan", []),
        )

    graph = StateGraph(ResearchState)
    graph.add_node("research", retrieve_and_write)
    graph.add_edge(START, "research")
    graph.add_edge("research", END)
    return graph.compile()
