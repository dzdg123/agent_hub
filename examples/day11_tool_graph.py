from __future__ import annotations

import argparse
import asyncio
from research_agent.tool_graph import build_tool_graph, create_tool_graph_state
from research_agent.tools import builtin_registry


class MockChatModel:
    def __init__(self, case: str):
        self.case = case
        self.calls = 0

    def complete(self, messages, *, tools=None):
        self.calls += 1

        if self.case == "direct_answer":
            return {"content": "不需要工具也能回答。", "tool_calls": []}

        if self.case == "empty_reply":
            return {"content": "", "tool_calls": []}

        if self.case == "unknown_tool" and self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "call-1", "name": "shell", "arguments": {}}
                ],
            }

        if self.case == "bad_arguments" and self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "calculator",
                        "arguments": {"expression": 123},
                    }
                ],
            }

        if self.case == "endless_tools":
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": f"call-{self.calls}",
                        "name": "calculator",
                        "arguments": {"expression": "2 + 3"},
                    }
                ],
            }

        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "calculator",
                        "arguments": {"expression": "2 + 3"},
                    }
                ],
            }

        tool_message = messages[-1]
        return {
            "content": f"模型读取到工具观察：{tool_message['content']}",
            "tool_calls": [],
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=(
            "direct_answer",
            "one_tool",
            "bad_arguments",
            "unknown_tool",
            "empty_reply",
            "endless_tools",
        ),
        default="one_tool",
    )
    parser.add_argument("--max-model-calls", type=int, default=3)
    args = parser.parse_args()

    model = MockChatModel(args.case)
    graph = build_tool_graph(model, builtin_registry())
    initial = create_tool_graph_state(
        "请计算 2 + 3",
        max_model_calls=args.max_model_calls,
    )
    result = await graph.ainvoke(initial, config={"recursion_limit": 20})

    print("status:", result["status"])
    print("stop_reason:", result["stop_reason"])
    print("model_calls:", result["model_calls"])
    print("trace:")
    for entry in result["trace"]:
        print(" -", entry)
    print("messages:")
    for message in result["messages"]:
        print(" -", message)
    print("mermaid:")
    print(graph.get_graph().draw_mermaid())


if __name__ == "__main__":
    asyncio.run(main())

