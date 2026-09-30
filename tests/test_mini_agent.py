import pytest
import json
from copy import deepcopy
from research_agent.demo_model import DemoModel
from research_agent.mini_agent import MiniAgent
from research_agent.tools import builtin_registry, Tool, ToolRegistry

from research_agent.llm import LLMError

from research_agent.models import (
    MiniAgentStatus,
    ModelReply,
    ToolCall,
    Usage,
)

class TwoToolModel:
    def __init__(self):
        self.calls = []

    async def complete(
        self,
        messages,
        *,
        tools=None,
        response_format=None,
    ):
        self.calls.append(deepcopy(messages))

        if len(self.calls) == 1:
            return ModelReply(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-first",
                        name="first",
                        arguments={},
                    ),
                    ToolCall(
                        id="call-second",
                        name="second",
                        arguments={},
                    ),
                ],
                usage=Usage(model_calls=1),
            )

        assert len(self.calls) == 2, "发生了多余的模型调用"

        return ModelReply(
            content="两个工具均已完成。",
            usage=Usage(model_calls=1),
        )


@pytest.fixture
def cancellation_case():
    executed = []

    def first_handler(arguments):
        executed.append("first")
        return {"value": 10}

    def second_handler(arguments):
        executed.append("second")
        return {"value": 20}

    registry = ToolRegistry([
        Tool(
            name="first",
            description="第一个测试工具",
            parameters={"type": "object", "properties": {}},
            handler=first_handler,
        ),
        Tool(
            name="second",
            description="第二个测试工具",
            parameters={"type": "object", "properties": {}},
            handler=second_handler,
        ),
    ])

    model = TwoToolModel()
    agent = MiniAgent(model, registry)

    return agent, model, executed

class FixedReplyModel:
    """每次返回固定回复，并保存实际收到的请求。"""

    def __init__(self, content: str):
        self.content = content
        self.calls = []

    async def complete(
        self,
        messages,
        *,
        tools=None,
        response_format=None,
    ):
        self.calls.append(deepcopy(messages))

        return ModelReply(
            content=self.content,
            request_id="test-request-1",
            usage=Usage(model_calls=1),
        )

@pytest.mark.asyncio
async def test_demo_agent_calls_calculator():
    answer, usage = await MiniAgent(DemoModel(), builtin_registry()).run("计算 12 * 8")
    assert "96" in answer
    assert usage.tool_calls == 1


@pytest.mark.asyncio
async def test_agent_honors_cancellation():
    answer, usage = await MiniAgent(DemoModel(), builtin_registry()).run(
        "计算 1+1", is_cancelled=lambda: True
    )
    assert answer == "任务已取消"
    assert usage.model_calls == 0

@pytest.mark.asyncio
async def test_agent_v0():
    answer, usage = await MiniAgent(DemoModel(), builtin_registry()).run(
        "计算 1+1"
    )
    assert "2" in answer
    assert usage.tool_calls == 1


@pytest.mark.parametrize("max_steps", [0, -1])
def test_agent_rejects_invalid_max_steps(max_steps):
    with pytest.raises(ValueError, match="max_steps"):
        MiniAgent(
            FixedReplyModel("你好"),
            builtin_registry(),
            max_steps=max_steps,
        )


@pytest.mark.asyncio
async def test_agent_completes_plain_answer():
    model = FixedReplyModel("API 是程序之间交互的接口。")
    agent = MiniAgent(model, builtin_registry())

    result = await agent.run_detailed("解释 API")

    assert result.status == MiniAgentStatus.COMPLETED
    assert result.stop_reason == "final_answer"
    assert result.answer == "API 是程序之间交互的接口。"

      # 验证模型真的只调用了一次。
    assert len(model.calls) == 1
    assert result.steps == 1
    assert result.usage.model_calls == 1
    assert result.usage.tool_calls == 0

    # 模型调用时只有初始消息。
    assert [m["role"] for m in model.calls[0]] == [
        "system",
        "user",
    ]

    # 结束后保存了最终回答。
    assert [m["role"] for m in result.messages] == [
        "system",
        "user",
        "assistant",
    ]
    assert result.messages[-1]["content"] == result.answer

    assert [event.kind for event in result.events] == [
        "run_started",
        "model_started",
        "model_finished",
        "run_finished",
    ]

    output = result.events[2].data["reply"]
    assert output["request_id"] == "test-request-1"
    assert output["usage"]["model_calls"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
async def test_agent_rejects_empty_answer(content):
    model = FixedReplyModel(content)
    agent = MiniAgent(model, builtin_registry())

    result = await agent.run_detailed("解释 API")

    assert result.status == MiniAgentStatus.FAILED
    assert result.stop_reason == "empty_response"
    assert len(model.calls) == 1
    assert result.usage.tool_calls == 0

    # 保留模型实际的空白输出，便于排查。
    assert result.messages[-1] == {
        "role": "assistant",
        "content": content,
    }

    assert result.events[-1].kind == "run_finished"
    assert sum(
        event.kind == "run_finished"
        for event in result.events
    ) == 1

@pytest.mark.asyncio
@pytest.mark.parametrize("first_is_invalid", [False, True])
async def test_agent_returns_tool_results_to_model(first_is_invalid):
    executed = []

    def first_handler(arguments):
        executed.append("first")
        return {"value": arguments["value"]}

    def second_handler(arguments):
        executed.append("second")
        return {"value": 20}

    registry = ToolRegistry([
        Tool(
            name="first",
            description="第一个测试工具",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
            handler=first_handler,
        ),
        Tool(
            name="second",
            description="第二个测试工具",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=second_handler,
        ),
    ])

    class TwoRoundModel:
        def __init__(self):
            self.calls = []

        async def complete(
            self,
            messages,
            *,
            tools=None,
            response_format=None,
        ):
            self.calls.append(deepcopy(messages))

            if len(self.calls) == 1:
                return ModelReply(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="call-first",
                            name="first",
                            arguments=(
                                {} if first_is_invalid else {"value": 10}
                            ),
                        ),
                        ToolCall(
                            id="call-second",
                            name="second",
                            arguments={},
                        ),
                    ],
                    usage=Usage(model_calls=1),
                )

            assert len(self.calls) == 2, "不应该出现第三轮调用"

            return ModelReply(
                content="已收到两份工具结果。",
                usage=Usage(model_calls=1),
            )

    model = TwoRoundModel()
    agent = MiniAgent(model, registry)

    result = await agent.run_detailed("执行两个测试工具")

    assert result.status == MiniAgentStatus.COMPLETED
    assert len(model.calls) == 2
    assert result.usage.tool_calls == 2

    # 验证传给第二轮模型的实际消息。
    second_input = model.calls[1]
    assert [message["role"] for message in second_input] == [
        "system",
        "user",
        "assistant",
        "tool",
        "tool",
    ]

    requests = second_input[2]["tool_calls"]
    assert [request["id"] for request in requests] == [
        "call-first",
        "call-second",
    ]

    tool_messages = second_input[3:]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "call-first",
        "call-second",
    ]

    first_result = json.loads(tool_messages[0]["content"])
    second_result = json.loads(tool_messages[1]["content"])

    if first_is_invalid:
        # 校验失败，第一项 handler 没执行。
        assert executed == ["second"]
        assert first_result["ok"] is False
        assert first_result["content"] is None
        assert "value" in first_result["error"]
    else:
        assert executed == ["first", "second"]
        assert first_result == {
            "ok": True,
            "content": {"value": 10},
            "error": None,
        }

    assert second_result == {
        "ok": True,
        "content": {"value": 20},
        "error": None,
    }

@pytest.mark.asyncio
async def test_agent_handles_model_error():
    class ErrorModel:
        def __init__(self):
            self.calls = 0

        async def complete(
            self,
            messages,
            *,
            tools=None,
            response_format=None,
        ):
            self.calls += 1
            raise LLMError("模拟模型服务不可用")

    model = ErrorModel()
    agent = MiniAgent(model, builtin_registry())

    result = await agent.run_detailed("解释 API")

    assert result.status == MiniAgentStatus.FAILED
    assert result.stop_reason == "model_error"
    assert "模拟模型服务不可用" in result.answer

    assert model.calls == 1
    assert result.steps == 1
    assert result.usage.model_calls == 0
    assert result.usage.tool_calls == 0

    assert [message["role"] for message in result.messages] == [
        "system",
        "user",
    ]

    assert [event.kind for event in result.events] == [
        "run_started",
        "model_started",
        "run_finished",
    ]

    error = result.events[-1].data["error"]
    assert error["type"] == "LLMError"
    assert error["message"] == "模拟模型服务不可用"

@pytest.mark.asyncio
async def test_agent_stops_at_max_steps():
    handler_calls = 0

    def handler(arguments):
        nonlocal handler_calls
        handler_calls += 1
        return {"value": handler_calls}

    registry = ToolRegistry([
        Tool(
            name="repeat",
            description="重复测试工具",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=handler,
        )
    ])

    class RepeatingToolModel:
        def __init__(self):
            self.calls = []

        async def complete(
            self,
            messages,
            *,
            tools=None,
            response_format=None,
        ):
            self.calls.append(deepcopy(messages))
            number = len(self.calls)

            return ModelReply(
                content="",
                tool_calls=[
                    ToolCall(
                        id=f"repeat-{number}",
                        name="repeat",
                        arguments={},
                    )
                ],
                usage=Usage(model_calls=1),
            )

    model = RepeatingToolModel()
    agent = MiniAgent(model, registry, max_steps=3)

    result = await agent.run_detailed("一直调用工具")

    assert result.status == MiniAgentStatus.STOPPED
    assert result.stop_reason == "max_steps"
    assert result.steps == 3

    assert len(model.calls) == 3
    assert handler_calls == 3
    assert result.usage.model_calls == 3
    assert result.usage.tool_calls == 3

    assert [message["role"] for message in result.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]

    assert result.messages[-1]["tool_call_id"] == "repeat-3"

    assert sum(
        event.kind == "model_started"
        for event in result.events
    ) == 3

    assert sum(
        event.kind == "tool_started"
        for event in result.events
    ) == 3

    assert result.events[-1].kind == "run_finished"


@pytest.mark.asyncio
async def test_cancelled_run_finishes_once():
    model = FixedReplyModel("不应被调用")
    agent = MiniAgent(model, builtin_registry())

    result = await agent.run_detailed(
        "解释 API",
        is_cancelled=lambda: True,
    )

    assert result.status == MiniAgentStatus.CANCELLED
    assert result.stop_reason == "user_cancelled"
    assert result.answer == "任务已取消"

    assert len(model.calls) == 0
    assert result.steps == 0
    assert result.usage.model_calls == 0
    assert result.usage.tool_calls == 0
    assert result.elapsed_seconds >= 0

    assert [event.kind for event in result.events] == [
        "run_started",
        "run_finished",
    ]

    assert sum(
        event.kind == "run_finished"
        for event in result.events
    ) == 1

'''day05阶段二实验 对照组'''
@pytest.mark.asyncio
async def test_no_cancellation_runs_both_tools(cancellation_case):
    agent, model, executed = cancellation_case

    result = await agent.run_detailed("执行两个工具")

    assert result.status == MiniAgentStatus.COMPLETED
    assert len(model.calls) == 2
    assert executed == ["first", "second"]
    assert result.usage.tool_calls == 2

