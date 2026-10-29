from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

from .models import Source, Usage
from .rag_models import AnswerResult, EvidenceScope


ResearchGraphStatus = Literal[
    "initialized",
    "planning",
    "retrieving",
    "curating",
    "writing",
    "validating",
    "awaiting_review",
    "completed",
    "no_evidence",
    "failed",
]

ResearchStopReason = Literal[
    "no_candidates",
    "no_allowed_sources",
    "budget_exhausted",
    "validation_failed",
    "model_failed",
    "unexpected_error",
]


class ResearchGraphState(TypedDict):
    """One run's data snapshot shared by the research graph nodes.

    This type contains values produced during a run. Service objects such as
    models, retrievers, settings, clients and callbacks are injected when the
    graph is built and must not be stored here.
    """

    # 初始化后保持稳定
    task_id: str
    query: str

    # 各节点覆盖
    plan: list[str]
    candidates: list[Source]
    evidence_scope: EvidenceScope | None
    answer_result: AnswerResult | None
    report_preview: str | None
    status: ResearchGraphStatus
    stop_reason: ResearchStopReason | None
    usage: Usage

    # 各节点只返回本节点产生的增量
    trace: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]


class ResearchGraphUpdate(TypedDict, total=False):
    """Fields that nodes may update.

    ``task_id`` and ``query`` are deliberately absent because nodes should
    treat both values as stable after initialization. For ``trace`` and
    ``errors``, return only entries created by the current node; their reducers
    append those entries to the existing state.
    """

    plan: list[str]
    candidates: list[Source]
    evidence_scope: EvidenceScope | None
    answer_result: AnswerResult | None
    report_preview: str | None
    status: ResearchGraphStatus
    stop_reason: ResearchStopReason | None
    usage: Usage
    trace: list[str]
    errors: list[str]


def create_research_graph_state(
    query: str,
    *,
    task_id: str | None = None,
) -> ResearchGraphState:
    """Create fresh, independent state for one graph invocation."""
    if not isinstance(query, str):
        raise TypeError("query 必须是字符串")
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query 不能为空")

    if task_id is None:
        normalized_task_id = str(uuid4())
    else:
        if not isinstance(task_id, str):
            raise TypeError("task_id 必须是字符串或 None")
        normalized_task_id = task_id.strip()
        if not normalized_task_id:
            raise ValueError("task_id 不能为空")

    return {
        "task_id": normalized_task_id,
        "query": normalized_query,
        "plan": [],
        "candidates": [],
        "evidence_scope": None,
        "answer_result": None,
        "report_preview": None,
        "status": "initialized",
        "stop_reason": None,
        "trace": [],
        "errors": [],
        "usage": Usage(),
    }


def accumulate_usage(current: Usage, delta: Usage) -> Usage:
    """Return ``current + delta`` without mutating either input object.

    ``Usage.add`` mutates its receiver, so graph nodes must copy the current
    snapshot before applying the usage produced by a model or tool call.
    The returned value is the complete accumulated value for the overwrite
    field ``ResearchGraphState.usage``.
    """
    if not isinstance(current, Usage) or not isinstance(delta, Usage):
        raise TypeError("current 和 delta 必须是 Usage")

    updated = current.model_copy(deep=True)
    updated.add(delta)
    return updated
