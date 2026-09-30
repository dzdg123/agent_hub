from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from time import perf_counter

from .llm import ChatModel, LLMError
from .models import MiniAgentResult, MiniAgentStatus, RunEvent, Usage
from .tools import ToolRegistry


EventCallback = Callable[[RunEvent], Awaitable[None]]


class MiniAgent:
    """第一周使用的不依赖框架的 Agent。"""

    def __init__(
        self,
        model: ChatModel,
        tools: ToolRegistry,
        *,
        max_steps: int = 6,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")

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
        """旧入口：保留 (answer, usage) 返回格式。"""
        result = await self.run_detailed(
            prompt,
            run_id=run_id,
            on_event=on_event,
            is_cancelled=is_cancelled,
        )
        return result.answer, result.usage

    async def run_detailed(
        self,
        prompt: str,
        *,
        run_id: str | None = None,
        on_event: EventCallback | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> MiniAgentResult:
        """新入口：执行循环，返回完整运行结果。"""
        started_at = perf_counter()

        # 每次调用都新建，避免多次运行之间共享历史与用量。
        result = MiniAgentResult(
            run_id=uuid.uuid4().hex if run_id is None else run_id,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是可靠的工具型助手。需要工具时调用工具；"
                        "得到结果后给出简洁答案。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        messages = result.messages
        usage = result.usage

        # 以下辅助函数只服务于本次运行。
        def cancelled() -> bool:
            return is_cancelled is not None and is_cancelled()

        async def emit(
            kind: str,
            message: str,
            data: dict | None = None,
        ) -> None:
            # 深拷贝让历史事件不会随后续 messages 的变化而改变。
            event_data = deepcopy(data) if data is not None else {}
            event_data["seq"] = len(result.events) + 1

            event = RunEvent(
                run_id=result.run_id,
                kind=kind,
                message=message,
                data=event_data,
            )
            result.events.append(event)

            if on_event is not None:
                # 回调拿到副本，避免修改已经保存的事件。
                await on_event(event.model_copy(deep=True))

        async def finish(
            status: MiniAgentStatus,
            answer: str,
            stop_reason: str,
            *,
            error: dict | None = None,
        ) -> MiniAgentResult:
            result.status = status
            result.answer = answer
            result.stop_reason = stop_reason
            result.elapsed_seconds = perf_counter() - started_at

            data = {
                "status": status.value,
                "stop_reason": stop_reason,
                "steps": result.steps,
                "answer": answer,
                "usage": usage.model_dump(),
                "elapsed_seconds": result.elapsed_seconds,
            }
            if error is not None:
                data["error"] = error

            await emit("run_finished", "运行结束", data)
            return result

        async def finish_cancelled() -> MiniAgentResult:
            return await finish(
                MiniAgentStatus.CANCELLED,
                "任务已取消",
                "user_cancelled",
            )

        await emit(
            "run_started",
            "运行开始",
            {
                "status": result.status.value,
                "max_steps": self.max_steps,
                "model_mode": getattr(self.model, "model_mode", "unknown"),
                "model_type": type(self.model).__name__,
            },
        )

        if cancelled():
            return await finish_cancelled()

        for step in range(1, self.max_steps + 1):
            if cancelled():
                return await finish_cancelled()

            definitions = self.tools.definitions()

            await emit(
                "model_started",
                f"准备调用模型，第 {step} 轮",
                {
                    "step": step,
                    "messages": messages,
                    "tools": definitions,
                },
            )

            # 事件回调可能设置了取消标志，需要再次检查。
            if cancelled():
                return await finish_cancelled()

            result.steps = step

            try:
                reply = await self.model.complete(
                    messages,
                    tools=definitions,
                )
            except LLMError as exc:
                # 只处理预期的模型服务错误，开发错误继续暴露。
                return await finish(
                    MiniAgentStatus.FAILED,
                    f"模型调用失败：{exc}",
                    "model_error",
                    error={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )

            usage.add(reply.usage)

            # 无论有无工具调用，都保存实际的 assistant 回复。
            assistant_message = {
                "role": "assistant",
                "content": reply.content,
            }

            if reply.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.arguments,
                                ensure_ascii=False,
                            ),
                        },
                    }
                    for call in reply.tool_calls
                ]

            messages.append(assistant_message)

            await emit(
                "model_finished",
                f"模型返回，第 {step} 轮",
                {
                    "step": step,
                    "reply": reply.model_dump(),
                },
            )

            # 已完成的回复与用量先保存，再响应取消。
            if cancelled():
                return await finish_cancelled()

            if not reply.tool_calls:
                if not reply.content.strip():
                    return await finish(
                        MiniAgentStatus.FAILED,
                        "模型没有返回有效回答",
                        "empty_response",
                    )

                return await finish(
                    MiniAgentStatus.COMPLETED,
                    reply.content,
                    "final_answer",
                )

            # 同一轮的工具按顺序执行。
            for call in reply.tool_calls:
                if cancelled():
                    return await finish_cancelled()

                tool_data = {
                    "step": step,
                    "tool_call_id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }

                await emit(
                    "tool_started",
                    f"准备调用工具 {call.name}",
                    tool_data,
                )

                if cancelled():
                    return await finish_cancelled()

                tool_started_at = perf_counter()
                usage.tool_calls += 1

                # 注意命名：不能覆盖外层的 Agent result。
                tool_result = await self.tools.invoke(
                    call.name,
                    call.arguments,
                )
                tool_elapsed = perf_counter() - tool_started_at

                # 即使 ok=False，也把失败结果交给下一轮模型。
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": tool_result.model_dump_json(),
                    }
                )

                await emit(
                    "tool_finished",
                    f"工具 {call.name} 返回",
                    {
                        **tool_data,
                        "result": tool_result.model_dump(),
                        "elapsed_seconds": tool_elapsed,
                    },
                )

                if cancelled():
                    return await finish_cancelled()

        return await finish(
            MiniAgentStatus.STOPPED,
            f"达到最大步骤数 {self.max_steps}，任务停止",
            "max_steps",
        )
