from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from .models import ModelReply, ToolCall, Usage


class DemoModel:
    """Deterministic offline model for tests and the first-day demo."""

    model_mode = "mock"

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> ModelReply:
        usage = Usage(prompt_tokens=10, completion_tokens=10, total_tokens=20, model_calls=1)
        latest = str(messages[-1].get("content", ""))
        if response_format:
            return ModelReply(content=json.dumps({"subqueries": [latest[:200]]}, ensure_ascii=False), usage=usage)
        if tools and messages[-1].get("role") == "user":
            expression = re.search(r"(?:计算|calculate)\s*([0-9+*/(). -]+)", latest, re.I)
            if expression:
                return ModelReply(
                    tool_calls=[
                        ToolCall(id="demo-call-1", name="calculator", arguments={"expression": expression.group(1).strip()})
                    ],
                    usage=usage,
                )
        if messages[-1].get("role") == "tool":
            return ModelReply(content=f"工具执行完成：{latest}", usage=usage)
        source_ids = list(dict.fromkeys(re.findall(r"\[((?:doc|web)-[^\]]+)\]", latest)))
        citations = " ".join(f"[{source_id}]" for source_id in source_ids[:3])
        if source_ids:
            return ModelReply(
                content=(
                    "# 离线演示研究报告\n\n"
                    f"## 摘要\n\n已根据提供的资料生成演示报告。{citations}\n\n"
                    f"## 分析\n\n这些资料展示了与研究问题相关的信息。{citations}\n\n"
                    "## 局限\n\n离线 DemoModel 不进行真实语言推理。\n\n"
                    "## 结论\n\n配置 DeepSeek API 后可生成正式报告。"
                ),
                usage=usage,
            )
        return ModelReply(content=f"离线演示回复：{latest}", usage=usage)
