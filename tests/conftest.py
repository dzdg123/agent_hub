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

    async def complete(self, messages, *, tools=None, response_format=None):
        self.calls.append(deepcopy(messages))
        self.tool_definitions.append(deepcopy(tools))
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
