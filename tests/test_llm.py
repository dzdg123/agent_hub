import json
from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [None, 512])
@respx.mock
async def test_output_limit_payload_and_finish_reason(limit):
    client = DeepSeekClient(Settings(deepseek_api_key="test-key-not-real"))
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
            "usage": {"total_tokens": 12},
        }),
    )
    reply = await client.complete(
        [{"role": "user", "content": "输出 JSON"}],
        response_format={"type": "json_object"}, max_tokens=limit,
    )
    payload = json.loads(route.calls[0].request.content)
    if limit is None:
        assert "max_tokens" not in payload
    else:
        assert payload["max_tokens"] == limit
    assert payload["response_format"] == {"type": "json_object"}
    assert reply.finish_reason == "length"
    assert reply.usage.total_tokens == 12
    assert reply.http_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
@respx.mock
async def test_client_rejects_invalid_output_limit_without_http(limit):
    client = DeepSeekClient(Settings(deepseek_api_key="test-key-not-real"))
    route = respx.post("https://api.deepseek.com/chat/completions")
    with pytest.raises(ValueError, match="max_tokens"):
        await client.complete([], max_tokens=limit)
    assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_complete_json_still_returns_schema_model():
    client = DeepSeekClient(Settings(deepseek_api_key="test-key-not-real"))
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps({
                "concept": "JSON", "explanation": "数据格式", "confidence": 1,
            })}, "finish_reason": "stop"}],
        }),
    )
    result = await client.complete_json(
        [{"role": "user", "content": "解释 JSON"}], ConceptExplanation,
    )
    assert isinstance(result, ConceptExplanation)
    assert result.concept == "JSON"
    assert "max_tokens" not in json.loads(route.calls[0].request.content)


@pytest.mark.asyncio
@respx.mock
async def test_rag_content_repair_and_network_retries_have_separate_limits(monkeypatch):
    from research_agent.models import Source
    from research_agent.rag import generate_answer, prepare_evidence_scope

    monkeypatch.setattr("research_agent.llm.asyncio.sleep", AsyncMock())
    source = Source(source_id="doc-a", title="实验", content="实验有三个步骤。")
    scope = prepare_evidence_scope([source], [source])
    good = json.dumps({
        "status": "answered",
        "claims": [{"text": "实验有三个步骤。", "kind": "fact", "evidence": [
            {"source_id": "doc-a", "quote": "实验有三个步骤。"},
        ]}],
        "limitations": [],
    }, ensure_ascii=False)

    def response(content, tokens):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"total_tokens": tokens},
        })

    route = respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=[
        httpx.Response(429), httpx.Response(503), response("坏 JSON", 10),
        httpx.Response(429), httpx.Response(503), response(good, 20),
    ])
    client = DeepSeekClient(Settings(deepseek_api_key="test-key-not-real"), retries=2)
    result = await generate_answer(client, "有几个步骤？", scope, max_tokens=512)
    assert result.status == "program_validated"
    assert route.call_count == 6
    assert len(result.attempts) == result.usage.model_calls == 2
    assert [attempt.http_attempts for attempt in result.attempts] == [3, 3]
    assert result.usage.total_tokens == 30
    assert all(json.loads(call.request.content)["max_tokens"] == 512 for call in route.calls)


@pytest.mark.asyncio
@respx.mock
async def test_rag_records_exhausted_http_attempts_without_content_repair(monkeypatch):
    from research_agent.models import Source
    from research_agent.rag import generate_answer, prepare_evidence_scope

    monkeypatch.setattr("research_agent.llm.asyncio.sleep", AsyncMock())
    source = Source(source_id="doc-a", title="资料", content="正文")
    scope = prepare_evidence_scope([source], [source])
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        side_effect=httpx.ReadTimeout("offline test"),
    )
    client = DeepSeekClient(Settings(deepseek_api_key="test-key-not-real"), retries=2)
    result = await generate_answer(client, "问题", scope)
    assert result.status == "model_failed"
    assert result.draft is None
    assert route.call_count == 3
    assert len(result.attempts) == 1
    assert result.attempts[0].http_attempts == 3


@pytest.mark.parametrize("retries", [-1, True, 1.5])
def test_client_rejects_invalid_retry_limit(retries):
    with pytest.raises(ValueError, match="retries"):
        DeepSeekClient(Settings(deepseek_api_key="test-key-not-real"), retries=retries)

