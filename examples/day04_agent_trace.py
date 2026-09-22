import asyncio
import json
from copy import deepcopy

from research_agent.mini_agent import MiniAgent
from research_agent.models import ModelReply, ToolCall, Usage
from research_agent.tools import builtin_registry


class CountDemoModel:
    def __init__(self, arguments=None):
        # 可替换参数，后面用于实验非法输入
        self.arguments = (
            {"text": "agent agent", "needle": "agent"}
            if arguments is None
            else arguments
        )

        # 保存每次模型调用开始时的消息
        self.snapshots = []

    async def complete(
        self, messages, *, tools=None, response_format=None
    ):
        self.snapshots.append(deepcopy(messages))
        usage = Usage(model_calls=1)

        if messages[-1]["role"] == "user":
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id="count-demo-1",
                        name="count_occurrences",
                        arguments=self.arguments,
                    )
                ],
                usage=usage,
            )

        if messages[-1]["role"] == "tool":
            payload = json.loads(messages[-1]["content"])

            if not payload["ok"]:
                return ModelReply(
                    content="工具失败：" + payload["error"],
                    usage=usage,
                )

            # 按你当前 handler 返回的 {"text": 次数} 读取
            count = payload["content"]["text"]

            return ModelReply(
                content=f"子串出现 {count} 次。",
                usage=usage,
            )

        raise AssertionError("出现了未预期的消息状态")


async def on_event(event):
    print(f"[{event.kind}] {event.message}")


async def main():
    model = CountDemoModel()
    agent = MiniAgent(model, builtin_registry())

    answer, usage = await agent.run(
        "统计 agent agent 中 agent 出现几次",
        on_event=on_event,
    )

    print("最终回答：", answer)
    print("模型调用次数：", usage.model_calls)
    print("工具调用次数：", usage.tool_calls)

    for index, messages in enumerate(model.snapshots, start=1):
        print(f"\n第 {index} 次模型调用前的 messages：")
        print(json.dumps(messages, ensure_ascii=False, indent=2))

    assert "2 次" in answer
    assert usage.model_calls == 2
    assert usage.tool_calls == 1

    # 第一次只有 system 和 user
    assert [m["role"] for m in model.snapshots[0]] == [
        "system", "user",
    ]

    # 第二次多了工具请求和工具结果
    second_messages = model.snapshots[1]
    assert [m["role"] for m in second_messages] == [
        "system", "user", "assistant", "tool",
    ]

    request = second_messages[-2]["tool_calls"][0]
    response = second_messages[-1]

    # 请求和结果必须对应同一次调用
    assert response["tool_call_id"] == request["id"]

    payload = json.loads(response["content"])
    assert payload == {
        "ok": True,
        "content": {"text": 2},
        "error": None,
    }

    await failure_experiment()

async def failure_experiment():
    model = CountDemoModel( {"text": "agent agent", "needle": ""})
    agent = MiniAgent(model, builtin_registry())

    answer, usage = await agent.run("非法参数测试")

    assert answer.startswith("工具失败：")
    assert usage.model_calls == 2
    assert usage.tool_calls == 1

    second_messages = model.snapshots[1]
    request = second_messages[-2]["tool_calls"][0]
    response = second_messages[-1]
    payload = json.loads(response["content"])

    assert response["tool_call_id"] == request["id"]
    assert payload["ok"] == False
    assert payload["content"] is None
    assert payload["error"]

    print(answer)



if __name__ == "__main__":
    asyncio.run(main())