from __future__ import annotations

import pytest

from research_agent.graph_state import (
    accumulate_usage,
    create_research_graph_state,
)
from research_agent.models import Source, Usage


def test_create_state_normalizes_input_and_preserves_explicit_task_id():
    state = create_research_graph_state(
        "  如何设计研究图？  ",
        task_id="  task-001  ",
    )

    assert state["task_id"] == "task-001"
    assert state["query"] == "如何设计研究图？"
    assert state["status"] == "initialized"
    assert state["stop_reason"] is None


@pytest.mark.parametrize("query", ["", "   "])
def test_create_state_rejects_blank_query(query: str):
    with pytest.raises(ValueError, match="query 不能为空"):
        create_research_graph_state(query)


def test_create_state_rejects_blank_explicit_task_id():
    with pytest.raises(ValueError, match="task_id 不能为空"):
        create_research_graph_state("问题", task_id="   ")


def test_two_runs_do_not_share_mutable_values():
    first = create_research_graph_state("第一个问题")
    second = create_research_graph_state("第二个问题")

    first["plan"].append("first-plan")
    first["candidates"].append(
        Source(source_id="source-1", title="示例", content="示例内容")
    )
    first["trace"].append("first-trace")
    first["errors"].append("first-error")
    first["usage"].model_calls = 2

    assert second["plan"] == []
    assert second["candidates"] == []
    assert second["trace"] == []
    assert second["errors"] == []
    assert second["usage"].model_calls == 0
    assert first["task_id"] != second["task_id"]


def test_accumulate_usage_returns_new_value_without_mutating_inputs():
    current = Usage(
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        model_calls=1,
        estimated_cost=0.01,
    )
    delta = Usage(
        prompt_tokens=20,
        completion_tokens=8,
        total_tokens=28,
        model_calls=1,
        estimated_cost=0.02,
    )

    result = accumulate_usage(current, delta)

    assert result.prompt_tokens == 30
    assert result.completion_tokens == 13
    assert result.total_tokens == 43
    assert result.model_calls == 2
    assert result.estimated_cost == pytest.approx(0.03)
    assert current.total_tokens == 15
    assert current.model_calls == 1
    assert delta.total_tokens == 28
    assert result is not current
    assert result is not delta
