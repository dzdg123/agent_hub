import asyncio
import json

from research_agent.tools import builtin_registry
from unittest import result


async def main():
    registry = builtin_registry()
    print(json.dumps(registry.definitions(),ensure_ascii=False, indent=2))

    cases = [
        ("calculator", {"expression": "12 * 8"}),
        ("current_time", {}),
        ("text_statistics", {"text": "hello agent"}),
        ("calculator", {}),
        ("unknown_tool", {}),
        ("calculator", {"expression": "1 / 0"}),
        ("calculator", {"expression": 123}),
        ("calculator", {"expression": "1+1", "unexpected": True}),
        ("current_time", {"timezone": "Asia/Shanghai"}),
        ("text_statistics", {"text": [1, 2, 3]}),
    ]

    for name, arg in cases:
        result = await registry.invoke(name, arg)
        print(name,result.model_dump())

if __name__ == "__main__":
    asyncio.run(main())