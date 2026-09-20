import pytest
import httpx
import respx
from pydantic import BaseModel, Field, Json

from research_agent.llm import DeepSeekClient, LLMResponseError,LLMError
from research_agent.config import Settings

class ConceptExplanation(BaseModel):
    concept: str
    explanation: str
    confidence: float = Field(ge=0, le=1)



def test_normalize_openai_compatible_tool_call():
    reply = DeepSeekClient._normalize(
        {
            "id": "request-1",
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {"name": "calculator", "arguments": '{"expression":"2+2"}'},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        0.1,
    )
    assert reply.tool_calls[0].arguments == {"expression": "2+2"}
    assert reply.usage.total_tokens == 5


@pytest.mark.asyncio
@respx.mock
async def test_complete_success():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )

    client = DeepSeekClient(settings,retries=2)

    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "id": "test_request",
                "choices": [
                    {
                        "message": {
                            "content": "你好",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )
    )
    reply = await client.complete([{"role":"user","content":"你好"}])
    assert reply.content == "你好"
    assert route.call_count == 1

@pytest.mark.asyncio
@respx.mock
async def test_complete_retries_after_429_then_succeeds():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )

    client = DeepSeekClient(settings,retries=2)
    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        side_effect=[
            httpx.Response(
                429,
                json={"error":{"message":"rate limit"}},
            ),
            httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json={
                    "id": "request-2",
                    "choices": [
                        {
                            "message": {
                                "content": "重试成功",
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            )
        ]
    )
    reply = await client.complete(
        [{"role":"user","content":"你好"}],

    )
    assert reply.content == "重试成功"
    assert route.call_count == 2

@pytest.mark.asyncio
@respx.mock
async def test_complete_retries_after_429_then_succeeds():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )

    client = DeepSeekClient(settings,retries=2)
    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        side_effect=[
            httpx.Response(
                429,
                json={"error":{"message":"rate limit"}},
            ),
            httpx.Response(
                429,
                json={"error": {"message": "rate limit"}},
            ),
            httpx.Response(
                429,
                json={"error": {"message": "rate limit"}},
            ),
        ]
    )
    with pytest.raises(LLMError) as exc_info:
        await client.complete(["role","user","content","你好"])
    assert "rate limit" in str(exc_info.value).lower() or "429" in str(exc_info.value)
    assert route.call_count == 3

@pytest.mark.asyncio
@respx.mock
async def test_complete_retries_after_400_then_succeeds():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )

    client = DeepSeekClient(settings,retries=2)
    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        side_effect=[
            httpx.Response(
                400,
                json={"error":{"message":"bad request"}},
            )
        ]
    )
    with pytest.raises(LLMError):
        await client.complete({"role":"user","content":"你好"})

    assert route.call_count == 1

@pytest.mark.asyncio
@respx.mock
async def test_complete_retries_after_on_timeout():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )
    client = DeepSeekClient(settings,retries=2)

    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        side_effect=httpx.ReadTimeout("网络请求超时")
    )

    with pytest.raises(LLMError,match="模型调用失败"):
        await client.complete([{"role":"user","content":"你好"}])

    assert route.call_count == 3

@pytest.mark.asyncio
@respx.mock
async def test_complete_retries_unavailable_input():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )

    client = DeepSeekClient(settings,retries=2)

    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        side_effect=[
            httpx.Response(
                200,
                text="这不是json"
            )
        ]
    )
    with pytest.raises(LLMResponseError):
        await client.complete([{"role":"user","content":"你好"}])

    assert route.call_count == 1

@pytest.mark.asyncio
@respx.mock
async def test_complete_json_rejects_invalid_json():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )

    client = DeepSeekClient(settings)
    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "id" : "request-1",
                "choices":[
                    {
                        "message":{
                            "content":'{"concept":"反序列化"'
                        }
                    }
                ],
                "usage":{},
            }
        )
    )

    with pytest.raises(LLMResponseError,match="结构化输出校验失败"):
        await client.complete_json(
            [{"role": "user", "content": "解释反序列化"}],
            ConceptExplanation
        )
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_complete_json_rejects_invalid_schema():
    settings = Settings(
        deepseek_api_key="test-key-not-real",
        deepseek_base_url="https://api.deepseek.com",
        request_timeout_seconds=0.1,
    )
    client = DeepSeekClient(settings)
    route = respx.post(
        "https://api.deepseek.com/chat/completions"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "id" : "request-1",
                "choices":[
                    {
                        "message":{
                            "content":(
                                '{"concept":"反序列化",'
                                '"explanation":"将数据恢复为 Python 对象",'
                                '"confidence":1.5}'
                            )
                        }
                    }
                ],
                "usage":{},
            }
        )
    )

    with pytest.raises(LLMResponseError,match="结构化输出校验失败"):
        await client.complete_json([{"role":"user","content":"解释反序列化"}], ConceptExplanation)



def test_normalize_rejects_missing_message():
    with pytest.raises(LLMResponseError):
        DeepSeekClient._normalize({}, 0.1)

