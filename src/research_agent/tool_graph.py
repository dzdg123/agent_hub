from __future__ import annotations

import inspect
import json
import operator
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph


class ToolCall(TypedDict):
    id: str
    name: str
    arguments: dict[str, Any]


class Message(TypedDict, total=False):
    role: str
    content: str
    name: str
    tool_call_id: str
    tool_calls: list[ToolCall]


class ToolGraphState(TypedDict):
    messages: Annotated[list[Message], operator.add]
    model_calls: int
    max_model_calls: int
    pending_tool_calls: list[ToolCall]
    status: Literal["running", "completed", "stopped", "failed"]
    stop_reason: str | None
    trace: Annotated[list[str], operator.add]


class ChatModel(Protocol):
    def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any: ...


class ToolRegistry(Protocol):
    def definitions(self) -> list[dict[str, Any]]: ...

    def invoke(self, name: str, arguments: dict[str, Any]) -> Any: ...


Route = Literal["tools", "end"]


def create_tool_graph_state(
    question: str,
    *,
    max_model_calls: int = 3,
) -> ToolGraphState:
    """Create fresh state for one graph run."""
    if not question.strip():
        raise ValueError("question must not be empty")
    if max_model_calls < 1:
        raise ValueError("max_model_calls must be at least 1")

    return {
        "messages": [{"role": "user", "content": question}],
        "model_calls": 0,
        "max_model_calls": max_model_calls,
        "pending_tool_calls": [],
        "status": "running",
        "stop_reason": None,
        "trace": [],
    }


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _normalise_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, Mapping):
            return dict(decoded)
    raise ValueError("tool call arguments must be an object")


def _normalise_tool_call(value: Any) -> ToolCall:
    function = _field(value, "function")
    call_id = _field(value, "id")
    name = _field(value, "name")
    arguments = _field(value, "arguments")

    # Also accept the common nested {function: {name, arguments}} shape.
    if function is not None:
        name = _field(function, "name", name)
        arguments = _field(function, "arguments", arguments)

    if not isinstance(call_id, str) or not call_id:
        raise ValueError("tool call is missing a non-empty id")
    if not isinstance(name, str) or not name:
        raise ValueError("tool call is missing a non-empty name")

    return {
        "id": call_id,
        "name": name,
        "arguments": _normalise_arguments(arguments),
    }


def _normalise_reply(reply: Any) -> tuple[str, list[ToolCall]]:
    content = _field(reply, "content", "")
    raw_tool_calls = _field(reply, "tool_calls", [])

    if content is None:
        content = ""
    if not isinstance(content, str):
        raise ValueError("model reply content must be a string")
    if raw_tool_calls is None:
        raw_tool_calls = []
    if not isinstance(raw_tool_calls, list):
        raise ValueError("model reply tool_calls must be a list")

    return content.strip(), [_normalise_tool_call(item) for item in raw_tool_calls]


def _tool_result_content(result: Any) -> str:
    """Turn ToolResult-like values into deterministic message content."""
    if isinstance(result, str):
        return result
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    elif hasattr(result, "to_dict"):
        result = result.to_dict()
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except TypeError:
        return str(result)


def _make_model_node(model: ChatModel, tool_registry: ToolRegistry):
    async def model_node(state: ToolGraphState) -> dict[str, Any]:
        if state["model_calls"] >= state["max_model_calls"]:
            return {
                "pending_tool_calls": [],
                "status": "stopped",
                "stop_reason": "max_model_calls",
                "trace": ["model:stopped:max_model_calls"],
            }

        next_count = state["model_calls"] + 1
        try:
            reply = model.complete(
                state["messages"],
                tools=tool_registry.definitions(),
            )
            if inspect.isawaitable(reply):
                reply = await reply
            content, tool_calls = _normalise_reply(reply)
        except Exception as exc:
            return {
                "model_calls": next_count,
                "pending_tool_calls": [],
                "status": "failed",
                "stop_reason": f"model_or_protocol_error:{type(exc).__name__}",
                "trace": ["model:failed"],
            }

        assistant_message: Message = {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        }

        # A final answer is successful even on the last allowed model call.
        if content and not tool_calls:
            return {
                "messages": [assistant_message],
                "model_calls": next_count,
                "pending_tool_calls": [],
                "status": "completed",
                "stop_reason": None,
                "trace": ["model:completed"],
            }

        # Do not execute a newly requested tool when no later model call is left.
        if tool_calls and next_count >= state["max_model_calls"]:
            return {
                "messages": [assistant_message],
                "model_calls": next_count,
                "pending_tool_calls": [],
                "status": "stopped",
                "stop_reason": "max_model_calls",
                "trace": ["model:stopped:max_model_calls"],
            }

        if tool_calls:
            return {
                "messages": [assistant_message],
                "model_calls": next_count,
                "pending_tool_calls": tool_calls,
                "status": "running",
                "stop_reason": None,
                "trace": ["model:requested_tools"],
            }

        return {
            "messages": [assistant_message],
            "model_calls": next_count,
            "pending_tool_calls": [],
            "status": "failed",
            "stop_reason": "empty_model_reply",
            "trace": ["model:failed:empty_reply"],
        }

    return model_node


def _make_tools_node(tool_registry: ToolRegistry):
    async def tools_node(state: ToolGraphState) -> dict[str, Any]:
        messages: list[Message] = []
        trace: list[str] = []

        for call in state["pending_tool_calls"]:
            try:
                result = tool_registry.invoke(
                    call["name"],
                    dict(call["arguments"]),
                )
                if inspect.isawaitable(result):
                    result = await result
                content = _tool_result_content(result)
                if bool(_field(result, "ok", True)):
                    trace.append(f"tools:success:{call['name']}")
                else:
                    trace.append(f"tools:error:{call['name']}")
            except Exception as exc:
                content = (
                    "error: tool registry failure: "
                    f"{type(exc).__name__}: {exc}"
                )
                trace.append(f"tools:error:{call['name']}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": content,
                }
            )

        return {
            "messages": messages,
            "pending_tool_calls": [],
            "status": "running",
            "stop_reason": None,
            "trace": trace,
        }

    return tools_node


def route_after_model(state: ToolGraphState) -> Route:
    """Choose the next node without mutating state or causing side effects."""
    if state["status"] in {"completed", "failed", "stopped"}:
        return "end"
    if state["pending_tool_calls"]:
        return "tools"
    return "end"


def build_tool_graph(
    model: ChatModel,
    tool_registry: ToolRegistry,
):
    builder = StateGraph(ToolGraphState)
    builder.add_node("model", _make_model_node(model, tool_registry))
    builder.add_node("tools", _make_tools_node(tool_registry))
    builder.add_edge(START, "model")
    builder.add_conditional_edges(
        "model",
        route_after_model,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "model")
    return builder.compile()

