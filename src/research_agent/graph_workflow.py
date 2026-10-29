"""Inspectable five-node research graph built from partial state updates.

This module intentionally lives beside the older ``workflow.build_langgraph``
entry point.  The old entry point wraps the whole workflow in one node; this
one exposes planning, retrieval, evidence curation, writing and validation as
separate nodes for Day 11 learning and testing.
"""

from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Literal, Protocol, cast

from langgraph.graph import END, START, StateGraph

from .graph_state import (
    ResearchGraphState,
    ResearchGraphUpdate,
    ResearchStopReason,
    accumulate_usage,
)
from .llm import ChatModel
from .models import Source
from .rag import generate_answer, prepare_evidence_scope
from .rag_models import AnswerResult, EvidenceScope
from .rag_render import render_answer_preview
from .retrieval_pipeline import TwoBranchRetriever


class ResearchRetriever(Protocol):
    """Small retrieval boundary consumed by the graph."""

    def retrieve(
        self,
        query: str,
        plan: list[str],
        *,
        filters: dict[str, set[str]] | None = None,
    ) -> list[Source] | Awaitable[list[Source]]: ...


class ResearchAnswerService(Protocol):
    """Small Day 10 answer-generation boundary consumed by the graph."""

    def generate(
        self,
        question: str,
        scope: EvidenceScope,
    ) -> AnswerResult | Awaitable[AnswerResult]: ...


@dataclass(frozen=True)
class Day09RetrieverAdapter:
    """Adapt the Day 09 two-branch retriever to the graph boundary.

    Subqueries are executed serially for the Day 11 graph.  Results are
    de-duplicated by ``source_id`` while preserving first-seen order.  Parallel
    merge semantics are deliberately left for Day 13.
    """

    retriever: TwoBranchRetriever
    candidate_k: int = 6
    top_k: int = 3
    rank_constant: int = 60
    allow_degraded: bool = False

    def retrieve(
        self,
        query: str,
        plan: list[str],
        *,
        filters: dict[str, set[str]] | None = None,
    ) -> list[Source]:
        queries = plan or [query]
        by_id: dict[str, Source] = {}

        for subquery in queries:
            result = self.retriever.search(
                subquery,
                candidate_k=self.candidate_k,
                top_k=self.top_k,
                rank_constant=self.rank_constant,
                filters=filters,
                allow_degraded=self.allow_degraded,
            )
            if result.status == "failed":
                raise RuntimeError(result.failure_reason or "检索失败")
            for source in result.final_sources or []:
                by_id.setdefault(source.source_id, source.model_copy(deep=True))

        return list(by_id.values())


@dataclass(frozen=True)
class Day10AnswerService:
    """Use the existing Day 10 generation and validation pipeline."""

    model: ChatModel
    max_tokens: int | None = None

    async def generate(
        self,
        question: str,
        scope: EvidenceScope,
    ) -> AnswerResult:
        return await generate_answer(
            self.model,
            question,
            scope,
            max_tokens=self.max_tokens,
        )


@dataclass(frozen=True)
class ResearchGraphServices:
    """Capabilities and configuration injected into graph nodes.

    These values are dependencies, not one-run state.  They therefore stay out
    of ``ResearchGraphState``.
    """

    retriever: ResearchRetriever
    answer_service: ResearchAnswerService
    canonical_sources: tuple[Source, ...]
    filters: dict[str, set[str]] | None = None
    max_context_chars: int = 2000
    base_dir: Path | None = None

    def __post_init__(self) -> None:
        if type(self.max_context_chars) is not int or self.max_context_chars <= 0:
            raise ValueError("max_context_chars 必须为正整数，不能是 bool")


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _safe_error(node: str, exc: Exception) -> str:
    """Keep state diagnostics useful without storing exception objects."""
    return f"{node}: {type(exc).__name__}: {exc}"


def _copy_filters(
    filters: dict[str, set[str]] | None,
) -> dict[str, set[str]] | None:
    if filters is None:
        return None
    return {name: set(values) for name, values in filters.items()}


def _stop_reason_for_answer(result: AnswerResult) -> ResearchStopReason:
    if result.status == "model_failed":
        return "model_failed"
    if result.status == "validation_failed":
        return "validation_failed"
    return "unexpected_error"


def _make_plan_node():
    def plan_node(state: ResearchGraphState) -> ResearchGraphUpdate:
        # Day 11 keeps planning deterministic.  Day 12 can replace this node
        # without changing the rest of the graph contract.
        return {
            "plan": [state["query"]],
            "status": "retrieving",
            "stop_reason": None,
            "trace": ["plan:completed"],
        }

    return plan_node


def _make_retrieve_node(services: ResearchGraphServices):
    async def retrieve_node(state: ResearchGraphState) -> ResearchGraphUpdate:
        try:
            candidates = await _resolve(
                services.retriever.retrieve(
                    state["query"],
                    list(state["plan"]),
                    filters=_copy_filters(services.filters),
                )
            )
            if not isinstance(candidates, list) or any(
                not isinstance(source, Source) for source in candidates
            ):
                raise TypeError("retriever 必须返回 list[Source]")
            snapshot = [source.model_copy(deep=True) for source in candidates]
            return {
                "candidates": snapshot,
                "status": "curating",
                "stop_reason": None,
                "trace": [f"retrieve:found:{len(snapshot)}"],
            }
        except Exception as exc:
            return {
                "candidates": [],
                "status": "failed",
                "stop_reason": "unexpected_error",
                "errors": [_safe_error("retrieve", exc)],
                "trace": ["retrieve:failed"],
            }

    return retrieve_node


def _make_curate_node(services: ResearchGraphServices):
    def curate_node(state: ResearchGraphState) -> ResearchGraphUpdate:
        try:
            scope = prepare_evidence_scope(
                [source.model_copy(deep=True) for source in services.canonical_sources],
                [source.model_copy(deep=True) for source in state["candidates"]],
                filters=_copy_filters(services.filters),
                max_context_chars=services.max_context_chars,
            )
        except Exception as exc:
            return {
                "evidence_scope": None,
                "status": "failed",
                "stop_reason": "unexpected_error",
                "errors": [_safe_error("curate", exc)],
                "trace": ["curate:failed"],
            }

        if scope.status != "ready":
            return {
                "evidence_scope": scope,
                "status": "no_evidence",
                "stop_reason": cast(ResearchStopReason, scope.status),
                "trace": [f"curate:{scope.status}"],
            }

        return {
            "evidence_scope": scope,
            "status": "writing",
            "stop_reason": None,
            "trace": [
                f"curate:ready:{len(scope.visible_sources)}"
            ],
        }

    return curate_node


def _make_write_node(services: ResearchGraphServices):
    async def write_node(state: ResearchGraphState) -> ResearchGraphUpdate:
        scope = state["evidence_scope"]
        if scope is None or scope.status != "ready":
            return {
                "status": "failed",
                "stop_reason": "unexpected_error",
                "errors": ["write: 缺少 ready 状态的 evidence_scope"],
                "trace": ["write:failed"],
            }

        try:
            result = await _resolve(
                services.answer_service.generate(state["query"], deepcopy(scope))
            )
            if not isinstance(result, AnswerResult):
                raise TypeError("answer_service 必须返回 AnswerResult")
        except Exception as exc:
            return {
                "status": "failed",
                "stop_reason": "unexpected_error",
                "errors": [_safe_error("write", exc)],
                "trace": ["write:failed"],
            }

        # AnswerResult.usage already includes every generation/repair attempt.
        # Accumulate that complete value once; do not add attempts again.
        usage = accumulate_usage(state["usage"], result.usage)
        if result.status != "program_validated":
            return {
                "answer_result": result,
                "usage": usage,
                "status": "failed",
                "stop_reason": _stop_reason_for_answer(result),
                "errors": [result.message or f"回答生成失败：{result.status}"],
                "trace": [f"write:{result.status}"],
            }

        return {
            "answer_result": result,
            "usage": usage,
            "status": "validating",
            "stop_reason": None,
            "trace": ["write:program_validated"],
        }

    return write_node


def _make_validate_node(services: ResearchGraphServices):
    def validate_node(state: ResearchGraphState) -> ResearchGraphUpdate:
        result = state["answer_result"]
        scope = state["evidence_scope"]
        if result is None or scope is None or scope.status != "ready":
            return {
                "report_preview": None,
                "status": "failed",
                "stop_reason": "unexpected_error",
                "errors": ["validate: 缺少回答结果或可见证据"],
                "trace": ["validate:failed"],
            }
        if result.status != "program_validated":
            return {
                "report_preview": None,
                "status": "failed",
                "stop_reason": _stop_reason_for_answer(result),
                "errors": [f"validate: 不可验证的回答状态 {result.status}"],
                "trace": ["validate:failed"],
            }
        if result.support_review != "pending":
            return {
                "report_preview": None,
                "status": "failed",
                "stop_reason": "validation_failed",
                "errors": [
                    "validate: 学习图只为 pending 草稿生成待审预览"
                ],
                "trace": ["validate:failed"],
            }

        try:
            preview = render_answer_preview(
                result,
                scope.visible_sources,
                base_dir=services.base_dir,
            )
        except Exception as exc:
            return {
                "report_preview": None,
                "status": "failed",
                "stop_reason": "validation_failed",
                "errors": [_safe_error("validate", exc)],
                "trace": ["validate:failed"],
            }

        return {
            "report_preview": preview,
            "status": "awaiting_review",
            "stop_reason": None,
            "trace": ["validate:awaiting_review"],
        }

    return validate_node


def _no_evidence_node(state: ResearchGraphState) -> ResearchGraphUpdate:
    scope = state["evidence_scope"]
    reason = state["stop_reason"] or "no_candidates"
    message = (
        scope.message
        if scope is not None and scope.message
        else "当前提供的资料不足，未调用模型生成回答。"
    )
    return {
        "report_preview": None,
        "status": "no_evidence",
        "errors": [message],
        "trace": [f"no_evidence:{reason}"],
    }


def _route_after_retrieve(
    state: ResearchGraphState,
) -> Literal["curate", "end"]:
    return "end" if state["status"] == "failed" else "curate"


def _route_after_curate(
    state: ResearchGraphState,
) -> Literal["write", "no_evidence", "end"]:
    if state["status"] == "failed":
        return "end"
    if state["status"] == "no_evidence":
        return "no_evidence"
    return "write"


def _route_after_write(
    state: ResearchGraphState,
) -> Literal["validate", "end"]:
    return "end" if state["status"] == "failed" else "validate"


def build_research_graph(services: ResearchGraphServices):
    """Build and compile the independent five-node research graph."""
    builder = StateGraph(ResearchGraphState)
    builder.add_node("plan", _make_plan_node())
    builder.add_node("retrieve", _make_retrieve_node(services))
    builder.add_node("curate", _make_curate_node(services))
    builder.add_node("write", _make_write_node(services))
    builder.add_node("validate", _make_validate_node(services))
    builder.add_node("no_evidence", _no_evidence_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"curate": "curate", "end": END},
    )
    builder.add_conditional_edges(
        "curate",
        _route_after_curate,
        {"write": "write", "no_evidence": "no_evidence", "end": END},
    )
    builder.add_conditional_edges(
        "write",
        _route_after_write,
        {"validate": "validate", "end": END},
    )
    builder.add_edge("validate", END)
    builder.add_edge("no_evidence", END)
    return builder.compile()
