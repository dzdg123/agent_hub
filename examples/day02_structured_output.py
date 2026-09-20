import asyncio
from pydantic import BaseModel, Field

from research_agent.config import Settings
from research_agent.llm import DeepSeekClient



class ConceptExplanation(BaseModel):
    concept: str
    explanation: str
    confidence: float = Field(ge=0,le=1)

async def main() -> None:
    settings = Settings()
    print("API Key 是否读取成功：", bool(settings.deepseek_api_key))

    client = DeepSeekClient(settings)

    messages = [
        {
            "role": "user",
            "content":(
                "你是一个编程学习助手。"
                "请只返回合法 JSON，不要输出 Markdown、代码块或其他文字。"
                "JSON 必须包含 concept、explanation、confidence 三个字段。"
                "confidence 必须是 0 到 1 之间的数字。"
            ),
        },
        {
            "role": "user",
            "content":"请解释python中的反序列话"
        }
    ]

    result = await client.complete_json(messages,ConceptExplanation,)

    print(result)
    print(f"概念：{result.concept}")
    print(f"解释：{result.explanation}")
    print(f"置信度：{result.confidence}")

if __name__ == "__main__":
    asyncio.run(main())