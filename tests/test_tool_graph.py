from __future__ import annotations

import asyncio

from research_agent.tool_graph import build_tool_graph, create_tool_graph_state


class RecordingRegistry:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def definitions(self):
        return [{"type": "function", "function": {"name": "calculator"}}]

    async def invoke(self, name: str, arguments: dict):
        self.calls.append((name, arguments))
        return {"ok": True, "content": arguments["a"] + arguments["b"]}


class OneToolModel:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, *, tools=None):
        self.calls += 1
        assert tools
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "calculator",
                        "arguments": {"a": 2, "b": 3},
                    }
                ],
            }
        assert messages[-1]["role"] == "tool"
        assert messages[-1]["tool_call_id"] == "call-1"
        return {"content": "结果是 5", "tool_calls": []}


class EndlessToolsModel:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, *, tools=None):
        self.calls += 1
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": f"call-{self.calls}",
                    "name": "calculator",
                    "arguments": {"a": 2, "b": 3},
                }
            ],
        }


class FinalAnswerOnLastCallModel:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, *, tools=None):
        self.calls += 1
        if self.calls < 3:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call-{self.calls}",
                        "name": "calculator",
                        "arguments": {"a": 2, "b": 3},
                    }
                ],
            }
        return {"content": "第三次调用给出最终答案", "tool_calls": []}


def invoke(graph, *, max_model_calls=3):
    return asyncio.run(
        graph.ainvoke(
            create_tool_graph_state(
                "请计算 2 + 3",
                max_model_calls=max_model_calls,
            ),
            config={"recursion_limit": 20},
        )
    )


def test_one_tool_then_final_answer():
    model = OneToolModel()
    registry = RecordingRegistry()
    result = invoke(build_tool_graph(model, registry))

    assert result["status"] == "completed"
    assert result["stop_reason"] is None
    assert result["model_calls"] == 2
    assert len(registry.calls) == 1
    assert result["trace"] == [
        "model:requested_tools",
        "tools:success:calculator",
        "model:completed",
    ]


def test_endless_tools_stops_before_third_tool_execution():
    model = EndlessToolsModel()
    registry = RecordingRegistry()
    result = invoke(build_tool_graph(model, registry))

    assert result["status"] == "stopped"
    assert result["stop_reason"] == "max_model_calls"
    assert result["model_calls"] == 3
    assert len(registry.calls) == 2


def test_final_answer_on_last_allowed_call_completes():
    model = FinalAnswerOnLastCallModel()
    registry = RecordingRegistry()
    result = invoke(build_tool_graph(model, registry))

    assert result["status"] == "completed"
    assert result["stop_reason"] is None
    assert result["model_calls"] == 3
    assert len(registry.calls) == 2


def test_two_runs_have_independent_state():
    first = invoke(build_tool_graph(OneToolModel(), RecordingRegistry()))
    second = invoke(build_tool_graph(OneToolModel(), RecordingRegistry()))

    assert first["trace"] == second["trace"]
    assert first["trace"] is not second["trace"]

