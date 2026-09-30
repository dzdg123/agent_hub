"""运行：python examples/day05_agent_v0.py；全程离线，仅导出合成数据。"""

import asyncio
import json
from pathlib import Path
import sys

from research_agent.llm import LLMError
from research_agent.mini_agent import MiniAgent
from research_agent.models import MiniAgentStatus, ModelReply, ToolCall, Usage
from research_agent.tools import builtin_registry
from research_agent.trace import save_trace


class ScenarioModel:
    """演示专用模型：固定请求工具，最终回答读取实际工具结果。"""

    model_mode = "mock"

    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = 0

    async def complete(self, messages, *, tools=None, response_format=None):
        self.calls += 1
        if self.scenario == "failed":
            raise LLMError("离线演示：模拟模型服务不可用")
        usage = Usage(model_calls=1)
        if self.calls == 1 or self.scenario == "stopped":
            calls = [ToolCall(
                id=f"calc-{self.calls}", name="calculator", arguments={"expression": "12 * 8"},
            )]
            if self.scenario == "cancelled":
                calls.append(ToolCall(id="time-1", name="current_time", arguments={}))
            return ModelReply(tool_calls=calls, usage=usage, request_id=f"demo-{self.calls}")
        payload = json.loads(messages[-1]["content"])
        answer = f"计算结果是 {payload['content']}。" if payload["ok"] else f"工具失败：{payload['error']}"
        return ModelReply(content=answer, usage=usage, request_id=f"demo-{self.calls}")


async def run_scenario(scenario, output_dir):
    cancelled = False

    async def on_event(event):
        nonlocal cancelled
        print(f"  {event.data['seq']:02d} [{event.kind}] {event.message}")
        if scenario == "cancelled" and event.kind == "tool_finished":
            cancelled = True

    model = ScenarioModel(scenario)
    agent = MiniAgent(model, builtin_registry(), max_steps=3)
    result = await agent.run_detailed(
        "计算 12 * 8；取消实验额外请求时间工具",
        on_event=on_event,
        is_cancelled=lambda: cancelled,
    )
    expected = {
        "completed": (MiniAgentStatus.COMPLETED, "final_answer", 2, 1),
        "failed": (MiniAgentStatus.FAILED, "model_error", 1, 0),
        "cancelled": (MiniAgentStatus.CANCELLED, "user_cancelled", 1, 1),
        "stopped": (MiniAgentStatus.STOPPED, "max_steps", 3, 3),
    }
    assert (result.status, result.stop_reason, model.calls, result.usage.tool_calls) == expected[scenario]
    assert result.events[-1].kind == "run_finished"
    events_path, result_path = save_trace(result, output_dir)
    print(f"运行 ID：{result.run_id}")
    print(f"状态：{result.status.value}；原因：{result.stop_reason}")
    print(f"回答：{result.answer}")
    print(f"步骤：{result.steps}；实际模型调用：{model.calls}；已返回用量中的模型调用：{result.usage.model_calls}")
    print(f"工具请求：{result.usage.tool_calls}；总耗时：{result.elapsed_seconds:.6f}s")
    print(f"事件：{events_path}\n完整结果：{result_path}")
    return result


async def main():
    output_dir = Path(__file__).resolve().parents[1] / "data" / "day05"
    for scenario in ("completed", "failed", "cancelled", "stopped"):
        print(f"\n=== 合成场景：{scenario} ===")
        await run_scenario(scenario, output_dir)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
