from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Sequence
from json import JSONDecodeError
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings
from .models import ModelReply, ToolCall, Usage


class LLMError(RuntimeError):
    """Base error for model calls."""


class LLMConfigurationError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class ChatModel(Protocol):
    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> ModelReply: ...


class DeepSeekClient:
    """Small OpenAI-compatible client with bounded retry and normalized output."""

    def __init__(self, settings: Settings, *, retries: int = 2) -> None:
        if not settings.deepseek_api_key:
            raise LLMConfigurationError("请设置 DEEPSEEK_API_KEY 后再调用真实模型")
        self.settings = settings
        self.retries = retries

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> ModelReply:
        payload: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": list(messages),
            "temperature": 0.1,
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            for attempt in range(self.retries + 1):
                try:
                    response = await client.post(
                        f"{self.settings.deepseek_base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()

                    try:
                        data = response.json()
                    except JSONDecodeError as exc:
                        raise LLMResponseError("模型响应不合法 JSON") from exc

                    return self._normalize(data, time.perf_counter() - started)

                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if exc.response.status_code not in {429, 500, 502, 503, 504}:
                        break
                if attempt < self.retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise LLMError(f"模型调用失败: {last_error}") from last_error

    @staticmethod
    def _normalize(data: dict[str, Any], elapsed: float) -> ModelReply:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("模型响应缺少 choices[0].message") from exc

        calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function", {})
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise LLMResponseError("工具参数不是合法 JSON") from exc
            calls.append(
                ToolCall(
                    id=raw.get("id", f"call-{len(calls)}"),
                    name=function.get("name", ""),
                    arguments=arguments,
                )
            )

        raw_usage = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
            model_calls=1,
            elapsed_seconds=elapsed,
        )
        return ModelReply(
            content=message.get("content") or "",
            tool_calls=calls,
            usage=usage,
            request_id=data.get("id"),
        )

    async def complete_json(
        self,
        messages: Sequence[dict[str, Any]],
        schema: type[BaseModel],
    ) -> BaseModel:
        reply = await self.complete(messages, response_format={"type": "json_object"})
        try:
            return schema.model_validate_json(reply.content)
        except ValidationError as exc:
            raise LLMResponseError(f"结构化输出校验失败: {exc}") from exc
