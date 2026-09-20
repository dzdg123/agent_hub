import pytest

from research_agent.demo_model import DemoModel
from research_agent.mini_agent import MiniAgent
from research_agent.tools import builtin_registry


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

