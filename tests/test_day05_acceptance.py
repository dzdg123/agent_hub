"""D05 固定案例：验证真实工具结果和边界，不依赖最终文本猜测行为。"""

import asyncio
from datetime import datetime, timedelta
import json
from unittest.mock import AsyncMock, Mock

import pytest

from research_agent.llm import LLMError
from research_agent.mini_agent import MiniAgent
from research_agent.models import MiniAgentResult, MiniAgentStatus, ModelReply, ToolCall, Usage
from research_agent.tools import builtin_registry
from research_agent.trace import save_trace


@pytest.fixture
def observed_registry(monkeypatch):
    registry = builtin_registry()
    # 仅测试层访问内部表：保留原 handler，观察实际执行而不替换返回值。
    handlers = {}
    for name, tool in registry._tools.items():
        handlers[name] = Mock(wraps=tool.handler)
        monkeypatch.setattr(tool, "handler", handlers[name])
    requests = AsyncMock(wraps=registry.invoke)
    monkeypatch.setattr(registry, "invoke", requests)
    return registry, handlers, requests


def tool_reply(name="calculator", arguments=None, call_id="call-1"):
    return ModelReply(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments or {})],
        request_id="request-1",
        usage=Usage(model_calls=1, prompt_tokens=5, completion_tokens=2, total_tokens=7),
    )


def final_reply():
    return ModelReply(content="已读取工具结果。", request_id="request-2", usage=Usage(model_calls=1))


def assert_terminal(result, status, reason):
    assert result.status == status
    assert result.stop_reason == reason
    assert result.elapsed_seconds >= 0
    assert result.events[0].kind == "run_started"
    assert result.events[0].data["model_mode"] == "mock"
    assert result.events[0].data["model_type"] == "ScriptedModel"
    assert [e.data["seq"] for e in result.events] == list(range(1, len(result.events) + 1))
    assert all(e.run_id == result.run_id for e in result.events)
    assert sum(e.kind == "run_finished" for e in result.events) == 1
    last = result.events[-1]
    assert last.kind == "run_finished"
    assert last.data["status"] == status
    assert last.data["stop_reason"] == reason
    assert last.data["steps"] == result.steps
    assert last.data["usage"] == result.usage.model_dump()
    assert last.data["answer"] == result.answer
    if status == MiniAgentStatus.COMPLETED:
        assert result.messages[-1] == {"role": "assistant", "content": result.answer}


def payloads(messages):
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


@pytest.mark.asyncio
async def test_d05_01_plain_answer(scripted_model, observed_registry):
    registry, handlers, requests = observed_registry
    model = scripted_model([ModelReply(content="API 是程序之间的接口。", usage=Usage(model_calls=1))])
    result = await MiniAgent(model, registry).run_detailed("用一句话解释 API")
    assert_terminal(result, MiniAgentStatus.COMPLETED, "final_answer")
    assert len(model.calls) == result.steps == result.usage.model_calls == 1
    assert result.usage.tool_calls == requests.await_count == 0
    assert all(handler.call_count == 0 for handler in handlers.values())
    assert [m["role"] for m in result.messages] == ["system", "user", "assistant"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name, arguments, expected, error_part, handler_count",
    [
        pytest.param("calculator", {"expression": "12 * 8"}, 96, None, 1, id="D05-02"),
        pytest.param("current_time", {}, None, None, 1, id="D05-03"),
        pytest.param("text_statistics", {"text": "hello agent"},
                     {"characters": 11, "non_whitespace": 10, "words": 2}, None, 1, id="D05-04"),
        pytest.param("count_occurrences", {"text": "Agent agent AGENT", "needle": "agent", "case_sensitive": False},
                     {"text": 3}, None, 1, id="D05-05"),
        pytest.param("unknown_tool", {}, None, "未知工具", 0, id="D05-06"),
        pytest.param("calculator", {}, None, "type=missing", 0, id="D05-07"),
        pytest.param("calculator", {"expression": 123}, None, "type=string_type", 0, id="D05-08-type"),
        pytest.param("calculator", {"expression": "1+1", "unexpected": True}, None,
                     "type=extra_forbidden", 0, id="D05-08-extra"),
        pytest.param("calculator", {"expression": "1 / 0"}, None, "ZeroDivisionError", 1, id="D05-09"),
    ],
)
async def test_d05_tool_roundtrip(scripted_model, observed_registry, name, arguments, expected, error_part, handler_count):
    registry, handlers, requests = observed_registry
    model = scripted_model([tool_reply(name, arguments), final_reply()])
    result = await MiniAgent(model, registry).run_detailed(f"执行 {name} 固定案例")
    assert_terminal(result, MiniAgentStatus.COMPLETED, "final_answer")
    assert len(model.calls) == result.steps == result.usage.model_calls == 2
    assert requests.await_count == result.usage.tool_calls == 1
    requests.assert_awaited_once_with(name, arguments)
    assert sum(handler.call_count for handler in handlers.values()) == handler_count
    if name in handlers:
        assert handlers[name].call_count == handler_count
    assert [m["role"] for m in model.calls[1]] == ["system", "user", "assistant", "tool"]
    request = model.calls[1][2]["tool_calls"][0]
    response = model.calls[1][3]
    assert request["id"] == response["tool_call_id"] == "call-1"
    assert request["function"]["name"] == name
    assert json.loads(request["function"]["arguments"]) == arguments
    payload = json.loads(response["content"])
    if error_part:
        assert payload["ok"] is False
        assert payload["content"] is None
        assert error_part in payload["error"]
        if handler_count == 0 and name == "calculator":
            assert payload["error"].startswith("参数校验失败:")
    else:
        assert payload["ok"] is True
        assert payload["error"] is None
        if name == "current_time":
            assert datetime.fromisoformat(payload["content"]).utcoffset() == timedelta(0)
        else:
            assert payload["content"] == expected
    finished = next(e for e in result.events if e.kind == "tool_finished")
    assert finished.data["tool_call_id"] == "call-1"
    assert finished.data["result"] == payload
    assert finished.data["elapsed_seconds"] >= 0
    model_event = next(e for e in result.events if e.kind == "model_finished")
    assert model_event.data["reply"]["request_id"] == "request-1"
    assert model_event.data["reply"]["usage"]["total_tokens"] == 7


def two_calls():
    return ModelReply(tool_calls=[
        ToolCall(id="calc-1", name="calculator", arguments={"expression": "2+2"}),
        ToolCall(id="calc-2", name="calculator", arguments={"expression": "3*3"}),
    ], usage=Usage(model_calls=1))


@pytest.mark.asyncio
async def test_d05_10_multiple_tools(scripted_model, observed_registry):
    registry, handlers, requests = observed_registry
    model = scripted_model([two_calls(), final_reply()])
    result = await MiniAgent(model, registry).run_detailed("分别计算 2+2 和 3*3")
    assert_terminal(result, MiniAgentStatus.COMPLETED, "final_answer")
    assert len(model.calls) == result.usage.model_calls == 2
    assert requests.await_count == handlers["calculator"].call_count == result.usage.tool_calls == 2
    assert [c.args[0]["expression"] for c in handlers["calculator"].call_args_list] == ["2+2", "3*3"]
    assert [m["tool_call_id"] for m in model.calls[1] if m["role"] == "tool"] == ["calc-1", "calc-2"]
    assert payloads(model.calls[1]) == [
        {"ok": True, "content": 4, "error": None},
        {"ok": True, "content": 9, "error": None},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", " ", "\n\t"])
async def test_d05_11_empty_reply(scripted_model, observed_registry, text):
    registry, _, requests = observed_registry
    model = scripted_model([ModelReply(content=text, usage=Usage(model_calls=1))])
    result = await MiniAgent(model, registry).run_detailed("空回复")
    assert_terminal(result, MiniAgentStatus.FAILED, "empty_response")
    assert len(model.calls) == result.steps == result.usage.model_calls == 1
    requests.assert_not_awaited()
    assert result.messages[-1] == {"role": "assistant", "content": text}


@pytest.mark.asyncio
async def test_d05_12_model_error(scripted_model, observed_registry):
    registry, handlers, requests = observed_registry
    model = scripted_model([LLMError("合成服务故障")])
    result = await MiniAgent(model, registry).run_detailed("模拟服务故障")
    assert_terminal(result, MiniAgentStatus.FAILED, "model_error")
    assert len(model.calls) == result.steps == 1
    assert result.usage.model_calls == 0  # 没有回复，用量未知，不能伪造。
    requests.assert_not_awaited()
    assert all(h.call_count == 0 for h in handlers.values())
    assert result.events[-1].data["error"] == {"type": "LLMError", "message": "合成服务故障"}


@pytest.mark.asyncio
async def test_d05_13_max_steps(scripted_model, observed_registry):
    registry, handlers, requests = observed_registry
    model = scripted_model([tool_reply(arguments={"expression": "1+1"}, call_id=f"repeat-{i}") for i in range(3)])
    result = await MiniAgent(model, registry, max_steps=3).run_detailed("持续调用")
    assert_terminal(result, MiniAgentStatus.STOPPED, "max_steps")
    assert len(model.calls) == result.steps == result.usage.model_calls == 3
    assert requests.await_count == handlers["calculator"].call_count == result.usage.tool_calls == 3
    assert result.messages[-1]["tool_call_id"] == "repeat-2"
    assert [len(payloads(messages)) for messages in model.calls] == [0, 1, 2]
    assert [p["content"] for p in payloads(result.messages)] == [2, 2, 2]


@pytest.mark.asyncio
async def test_d05_14_cancel_before_start(scripted_model, observed_registry):
    registry, handlers, requests = observed_registry
    model = scripted_model([])
    result = await MiniAgent(model, registry).run_detailed("取消", is_cancelled=lambda: True)
    assert_terminal(result, MiniAgentStatus.CANCELLED, "user_cancelled")
    assert len(model.calls) == result.steps == result.usage.model_calls == result.usage.tool_calls == 0
    requests.assert_not_awaited()
    assert all(h.call_count == 0 for h in handlers.values())
    assert [e.kind for e in result.events] == ["run_started", "run_finished"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_at, expected_models, expected_tools", [
    pytest.param("tool_finished", 1, 1, id="D05-15"),
    pytest.param("run_started", 0, 0, id="callback-run"),
    pytest.param("model_started", 0, 0, id="callback-model-start"),
    pytest.param("model_finished", 1, 0, id="callback-model-end"),
    pytest.param("tool_started", 1, 0, id="callback-tool-start"),
])
async def test_cancel_boundaries(scripted_model, observed_registry, cancel_at, expected_models, expected_tools):
    registry, handlers, requests = observed_registry
    model = scripted_model([two_calls()])
    cancel_requested = False

    async def on_event(event):
        nonlocal cancel_requested
        if event.kind == cancel_at:
            cancel_requested = True

    result = await MiniAgent(model, registry).run_detailed(
        "分别计算", on_event=on_event, is_cancelled=lambda: cancel_requested,
    )
    assert cancel_requested
    assert_terminal(result, MiniAgentStatus.CANCELLED, "user_cancelled")
    assert len(model.calls) == result.steps == result.usage.model_calls == expected_models
    assert requests.await_count == handlers["calculator"].call_count == result.usage.tool_calls == expected_tools
    assert result.events[-2].kind == cancel_at
    if expected_tools:
        assert payloads(result.messages) == [{"ok": True, "content": 4, "error": None}]
        assert result.messages[-1]["tool_call_id"] == "calc-1"
        assert [c["id"] for c in result.messages[2]["tool_calls"]] == ["calc-1", "calc-2"]


@pytest.mark.asyncio
async def test_run_isolation_and_snapshots(scripted_model):
    model = scripted_model([tool_reply(arguments={"expression": "1+1"}), final_reply(), final_reply()])
    agent = MiniAgent(model, builtin_registry())

    async def observer(event):
        # 不可信观察回调修改自己的副本，不能污染保存的事件。
        if event.kind == "model_started":
            event.data["messages"].clear()

    first = await agent.run_detailed("第一个问题", on_event=observer)
    frozen = first.model_dump()
    second = await agent.run_detailed("第二个问题")
    assert first.model_dump() == frozen
    assert first.run_id != second.run_id
    assert first.messages is not second.messages
    assert first.events is not second.events
    assert first.usage is not second.usage
    assert (first.usage.model_calls, first.usage.tool_calls, first.usage.total_tokens) == (2, 1, 7)
    assert (second.usage.model_calls, second.usage.tool_calls, second.usage.total_tokens) == (1, 0, 0)
    assert [m["content"] for m in second.messages if m["role"] == "user"] == ["第二个问题"]
    started = [e for e in first.events if e.kind == "model_started"]
    assert [len(e.data["messages"]) for e in started] == [2, 4]
    assert started[0].data["messages"] == model.calls[0]
    assert started[0].data["tools"] == model.tool_definitions[0]
    assert model.calls[2][1]["content"] == "第二个问题"
    assert_terminal(first, MiniAgentStatus.COMPLETED, "final_answer")
    assert_terminal(second, MiniAgentStatus.COMPLETED, "final_answer")


@pytest.mark.asyncio
async def test_programming_error_is_not_service_failure(scripted_model):
    agent = MiniAgent(scripted_model([AssertionError("开发错误")]), builtin_registry())
    with pytest.raises(AssertionError, match="开发错误"):
        await agent.run_detailed("不能吞掉开发错误")


@pytest.mark.asyncio
async def test_cancel_during_tool_preserves_finished_work(scripted_model, observed_registry, monkeypatch):
    registry, _, requests = observed_registry
    entered = asyncio.Event()
    release = asyncio.Event()
    executed = []
    cancelled = False

    async def delayed_handler(arguments):
        executed.append(arguments["expression"])
        entered.set()
        await release.wait()
        return 4

    monkeypatch.setattr(registry._tools["calculator"], "handler", delayed_handler)
    model = scripted_model([two_calls()])
    task = asyncio.create_task(MiniAgent(model, registry).run_detailed("取消边界", is_cancelled=lambda: cancelled))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        cancelled = True
        # 标志本身不打断正在等待的 handler。
        assert not task.done()
        release.set()
        result = await asyncio.wait_for(task, timeout=2)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert_terminal(result, MiniAgentStatus.CANCELLED, "user_cancelled")
    assert executed == ["2+2"]
    assert len(model.calls) == requests.await_count == 1
    assert payloads(result.messages) == [{"ok": True, "content": 4, "error": None}]


@pytest.mark.asyncio
async def test_trace_export_roundtrip(scripted_model, tmp_path):
    result = await MiniAgent(scripted_model([final_reply()]), builtin_registry()).run_detailed("合成轨迹")
    events_path, result_path = save_trace(result, tmp_path)
    exported = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert exported == [e.model_dump(mode="json") for e in result.events]
    assert MiniAgentResult.model_validate_json(result_path.read_text(encoding="utf-8")) == result
    before = events_path.read_bytes()
    with pytest.raises(FileExistsError):
        save_trace(result, tmp_path)
    assert events_path.read_bytes() == before
    unsafe = result.model_copy(update={"run_id": "../outside"})
    with pytest.raises(ValueError, match="UUID"):
        save_trace(unsafe, tmp_path)


@pytest.mark.asyncio
async def test_cli_ask_compatibility_offline(scripted_model, monkeypatch, capsys):
    from research_agent import cli

    model = scripted_model([tool_reply(arguments={"expression": "12*8"}), final_reply()])
    # 验证 ask 入口转发与二元组兼容；不读取本地密钥，不访问真实服务。
    settings = object()
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    client_factory = Mock(return_value=model)
    monkeypatch.setattr(cli, "DeepSeekClient", client_factory)
    await cli._execute("ask", "计算 12*8")
    client_factory.assert_called_once_with(settings)
    assert len(model.calls) == 2
    assert payloads(model.calls[1]) == [{"ok": True, "content": 96, "error": None}]
    output = capsys.readouterr().out
    assert "已读取工具结果。" in output
    assert "2 次模型调用, 1 次工具调用" in output
