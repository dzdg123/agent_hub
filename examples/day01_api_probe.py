import asyncio

from research_agent.config import get_settings
from research_agent.llm import DeepSeekClient

async def main() -> None:
    settings = get_settings()
    client = DeepSeekClient(settings)

    reply = await client.complete(
        [
            {"role": "system", "content": "你是一名耐心的 Python 入门老师。"},
            {"role": "user", "content": "告诉我什么是装饰器"}
        ]
    )

    print(f"模型：{settings.deepseek_model}")
    print(f"请求ID：{reply.request_id}")
    print(f"回答：{reply.content}")
    print(f"输入Tokens：{reply.usage.prompt_tokens}")
    print(f"输出Tokens：{reply.usage.completion_tokens}")
    print(f"总Tokens：{reply.usage.total_tokens}")
    print(f"耗时：{reply.usage.elapsed_seconds:.2f}秒")

if __name__ == "__main__":
    asyncio.run(main())