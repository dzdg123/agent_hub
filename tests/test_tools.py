import pytest

from research_agent.tools import builtin_registry, safe_calculate


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

