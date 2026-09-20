from __future__ import annotations

import ast
import operator
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


class ToolExecutionError(RuntimeError):
    pass


class ToolResult(BaseModel):
    ok: bool
    content: Any = None
    error: str | None = None


ToolHandler = Callable[[dict[str, Any]], Any | Awaitable[Any]]


class Tool:
    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
        read_only: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.read_only = read_only

    def as_model_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        self._validate_required(arguments)
        try:
            result = self.handler(arguments)
            if hasattr(result, "__await__"):
                result = await result
            return ToolResult(ok=True, content=result)
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    def _validate_required(self, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ToolExecutionError("工具参数必须是对象")
        missing = [key for key in self.parameters.get("required", []) if key not in arguments]
        if missing:
            raise ToolExecutionError(f"缺少必要参数: {', '.join(missing)}")


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools = {tool.name: tool for tool in tools or []}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已存在: {tool.name}")
        self._tools[tool.name] = tool

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.as_model_tool() for tool in self._tools.values()]

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"未知工具: {name}")
        try:
            return await tool.invoke(arguments)
        except ToolExecutionError as exc:
            return ToolResult(ok=False, error=str(exc))


_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}


def safe_calculate(expression: str) -> float:
    """Evaluate a deliberately tiny arithmetic grammar, never Python code."""

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = evaluate(node.left), evaluate(node.right)
            if abs(left) > 1e12 or abs(right) > 1e12:
                raise ValueError("数值过大")
            return _OPERATORS[type(node.op)](left, right)
        raise ValueError("表达式只允许数字和基本算术运算")

    if len(expression) > 100:
        raise ValueError("表达式过长")
    return evaluate(ast.parse(expression, mode="eval"))


def builtin_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                name="calculator",
                description="计算只包含数字、括号和基本运算符的算术表达式",
                parameters={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                    "additionalProperties": False,
                },
                handler=lambda args: safe_calculate(str(args["expression"])),
            ),
            Tool(
                name="current_time",
                description="返回当前 UTC 时间",
                parameters={"type": "object", "properties": {}, "additionalProperties": False},
                handler=lambda _: datetime.now(timezone.utc).isoformat(),
            ),
            Tool(
                name="text_statistics",
                description="统计一段文本的字符数、非空白字符数和词数",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                handler=lambda args: {
                    "characters": len(str(args["text"])),
                    "non_whitespace": len("".join(str(args["text"]).split())),
                    "words": len(str(args["text"]).split()),
                },
            ),
        ]
    )
