import pytest
import asyncio

from pydantic import BaseModel, ConfigDict
from research_agent.tools import builtin_registry, safe_calculate,Tool


def test_safe_calculate_accepts_arithmetic():
    assert safe_calculate("(12 + 3) * 2") == 30


@pytest.mark.parametrize("expression", ["__import__('os').system('dir')", "[1, 2]", "2 << 3"])
def test_safe_calculate_rejects_python(expression):
    with pytest.raises(ValueError):
        safe_calculate(expression)


@pytest.mark.asyncio
async def test_registry_validates_missing_arguments():
    result = await builtin_registry().invoke("calculator", {})
    assert not result.ok
    assert "缺少必要参数" in result.error


@pytest.mark.asyncio
async def test_registry_handles_unknown_tool():
    result = await builtin_registry().invoke("delete_everything", {})
    assert not result.ok
    assert "未知工具" in result.error

def test_validate_before_handeler():
    class TestArgs(BaseModel):
        model_config = ConfigDict(strict=True,extra='forbid')
        text: str

    call_count = 0
    def handler(args: TestArgs):
        nonlocal call_count
        call_count += 1
        return len(args["text"])

    tool = Tool(
        name="test_text_length",
        description="测试参数校验先于 handler 执行",
        input_model=TestArgs,
        handler=handler,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments, expected_count",
[
        ({"text": "banana", "needle": "an"}, 2),
        ({"text": "aaaa", "needle": "aa"}, 2),
        ({"text": "Hello hello", "needle": "hello"}, 1),
        (
            {
                "text": "Hello hello",
                "needle": "hello",
                "case_sensitive": False,
            },
            2,
        ),
        ({"text": "abc", "needle": "z"}, 0),
        ({"text": "", "needle": "a"}, 0),
    ],
)
async def test_tool_count_occurrences_vaild(arguments, expected_count):
    registry = builtin_registry()

    result = await registry.invoke("count_occurrences", arguments)

    assert result.ok is True, result.error
    assert result.content == {"text": expected_count}
    assert result.error is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {"text": "abc", "needle": ""},
        {"text": [1, 2, 3], "needle": "a"},
        {"text": "abc", "needle": 123},
        {"text": "abc", "needle": "a", "unexpected": True},
        {"text": "abc"},
        {"needle": "a"},
        {"text": "abc", "needle": "a", "case_sensitive": "false"},
        {"text": "a" * 10001, "needle": "a"},
        {"text": "abc", "needle": "a" * 101},
    ],
)
async def test_tool_count_occurrences_invalid(arguments):
    registry = builtin_registry()

    result = await registry.invoke("count_occurrences", arguments)
    assert result.ok is False, result.error
    assert result.content is None
    assert result.error is not None
    assert "参数校验失败" in result.error