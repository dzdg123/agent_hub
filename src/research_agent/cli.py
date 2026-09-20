from __future__ import annotations

import argparse
import asyncio
import sys

from .config import get_settings
from .demo_model import DemoModel
from .llm import DeepSeekClient
from .mini_agent import MiniAgent
from .tools import builtin_registry


async def _execute(command: str, prompt: str | None) -> None:
    settings = get_settings()
    if command == "demo":
        model = DemoModel()
        prompt = prompt or "计算 12 * 8"
    else:
        model = DeepSeekClient(settings)
        if not prompt:
            raise SystemExit("ask 命令需要一个问题")
    answer, usage = await MiniAgent(model, builtin_registry()).run(prompt)
    print(answer)
    print(f"\n用量: {usage.model_calls} 次模型调用, {usage.tool_calls} 次工具调用, {usage.total_tokens} tokens")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Research Agent learning CLI")
    parser.add_argument("command", choices=["demo", "ask"])
    parser.add_argument("prompt", nargs="?")
    args = parser.parse_args()
    asyncio.run(_execute(args.command, args.prompt))


if __name__ == "__main__":
    main()
