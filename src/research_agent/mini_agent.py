from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from .llm import ChatModel
from .models import ModelReply, RunEvent, Usage
from .tools import ToolRegistry


EventCallback = Callable[[RunEvent], Awaitable[None]]


class MiniAgent:
    """A framework-free model/tool loop used during week one."""

    def __init__(self, model: ChatModel, tools: ToolRegistry, *, max_steps: int = 6) -> None:
        self.model = model
        self.tools = tools
        self.max_steps = max_steps

    async def run(
        self,
        prompt: str,
        *,
        run_id: str = "cli",
        on_event: EventCallback | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> tuple[str, Usage]:
        messages: list[dict] = [
            {
                "role": "system",
                "content": "你是可靠的工具型助手。需要工具时调用工具；得到结果后给出简洁答案。",
            },
            {"role": "user", "content": prompt},
        ]
        usage = Usage()
        for step in range(1, self.max_steps + 1):
            if is_cancelled and is_cancelled():
                await self._emit(on_event, run_id, "cancelled", "任务已取消")
                return "任务已取消", usage
            await self._emit(on_event, run_id, "model", f"模型调用 {step}")
            reply = await self.model.complete(messages, tools=self.tools.definitions())
            usage.add(reply.usage)
            if not reply.tool_calls:
                return reply.content, usage

            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                        for call in reply.tool_calls
                    ],
                }
            )
            for call in reply.tool_calls:
                await self._emit(on_event, run_id, "tool", f"调用工具 {call.name}", call.arguments)
                result = await self.tools.invoke(call.name, call.arguments)
                usage.tool_calls += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result.model_dump_json(),
                    }
                )
        return f"达到最大步骤数 {self.max_steps}，任务停止", usage

    @staticmethod
    async def _emit(
        callback: EventCallback | None,
        run_id: str,
        kind: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        if callback:
            await callback(RunEvent(run_id=run_id, kind=kind, message=message, data=data or {}))

