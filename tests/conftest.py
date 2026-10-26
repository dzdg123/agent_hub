from copy import deepcopy

import pytest

from research_agent.models import ModelReply


class ScriptedModel:
    """离线按脚本返回；脚本耗尽立即失败，避免多余调用假通过。"""

    model_mode = "mock"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.tool_definitions = []
        self.response_formats = []
        self.output_limits = []

    async def complete(self, messages, *, tools=None, response_format=None, max_tokens=None):
        self.calls.append(deepcopy(messages))
        self.tool_definitions.append(deepcopy(tools))
        self.response_formats.append(deepcopy(response_format))
        self.output_limits.append(max_tokens)
        index = len(self.calls) - 1
        assert index < len(self.replies), "发生了预期之外的模型调用"
        item = self.replies[index]
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, ModelReply)
        return item.model_copy(deep=True)


@pytest.fixture
def scripted_model():
    return ScriptedModel


@pytest.fixture(autouse=True)
def forbid_real_embedding_in_day09_acceptance(request, monkeypatch):
    """关键行为验收若意外构造真实模型应立即失败，不依赖本机模型缓存。"""
    if request.node.get_closest_marker("day09_case") is None:
        return
    from research_agent.embeddings import SentenceTransformerEmbedder

    def forbidden(*args, **kwargs):
        pytest.fail("Day09关键行为测试不得加载真实Embedding；请使用假Embedder或独立实验脚本")

    monkeypatch.setattr(SentenceTransformerEmbedder, "__init__", forbidden)
