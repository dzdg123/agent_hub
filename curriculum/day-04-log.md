# Day 04 学习日志：工具调用链路

本次完成阶段一的源码阅读与链路梳理。以下示例是依据当前代码的推演，不是真实模型运行日志；未修改工具实现，未调用 API。

## 按指定顺序阅读 tools.py

| 阅读对象 | 职责与关键行为 |
|---|---|
| `ToolResult`（16 行） | 用 Pydantic 定义统一结果：`ok` 表示成功与否，`content` 默认 `None`，`error` 默认 `None`。它不是执行器，也不会校验工具输入。 |
| `Tool.__init__()`（26 行） | 保存名称、描述、参数 Schema、Python `handler` 和 `read_only`。此时没有执行 handler；`read_only` 当前只是属性。 |
| `Tool.as_model_tool()`（41 行） | 将名称、描述、参数 Schema 组成模型可读的 function 工具定义。没有把 handler 或 `read_only` 发给模型。 |
| `Tool.invoke()`（51 行） | 先校验 arguments，再调用 `handler(arguments)`。返回值带 `__await__` 时继续 await；成功包装为 `ToolResult(ok=True, content=result)`，handler 的普通异常包装为失败结果。 |
| `ToolRegistry.register()`（73 行） | 将工具存入按名称索引的 `_tools` 字典。同名注册抛出 `ValueError`，避免覆盖已有工具。 |
| `ToolRegistry.definitions()`（78 行） | 对所有已注册工具调用 `as_model_tool()`，返回供模型使用的定义列表，不执行工具。 |
| `ToolRegistry.invoke()`（81 行） | 按 name 查找工具；不存在则返回“未知工具”。存在则 await `tool.invoke(arguments)`，并把参数校验抛出的 `ToolExecutionError` 转成失败结果。 |
| `builtin_registry()`（124 行） | 构造 calculator、current_time、text_statistics 三个 Tool，并放进一个新的 ToolRegistry 返回。只是准备工具，不运行它们。 |

注意：上述是阅读顺序，不是运行顺序。实际先调用 `builtin_registry()` 构建注册表，再交给 MiniAgent 使用。该工厂通过 `ToolRegistry([...])` 初始化字典，并没有逐个调用 `register()`；构造器也没有 `register()` 的重复名称检查。

## 完整链路

```text
准备阶段：builtin_registry()
  → 创建三个 Tool（保存 Schema 与 handler）
  → ToolRegistry 保存 name → Tool 的映射
  → 将 registry 传给 MiniAgent

用户问题：请计算 12 * 8
  ↓
MiniAgent.run() 组装 system + user messages
  ↓
registry.definitions() → 每个 Tool.as_model_tool()
  ↓
model.complete(messages, tools=工具定义列表)
  ↓
模型返回工具调用请求
  → 真实客户端 llm.py 的 _normalize() 解析 arguments JSON 字符串
  → 得到 ToolCall(name="calculator", arguments={"expression":"12 * 8"}, id="call_demo_1")
  ↓
MiniAgent 先追加 role=assistant 的消息，保留 tool_calls 和调用 ID
  ↓
registry.invoke(call.name, call.arguments)
  → 从 _tools 按 name 查找已注册工具
  ↓
tool.invoke(arguments)
  → _validate_required()：必须是 dict，且包含 expression
  ↓
Python handler(arguments)
  → lambda args: safe_calculate(str(args["expression"]))
  → safe_calculate("12 * 8") → 96.0
  ↓
ToolResult(ok=True, content=96.0, error=None)
  ↓
MiniAgent 追加 role=tool 的消息
  → tool_call_id = "call_demo_1"
  → content = result.model_dump_json()
  ↓
下一轮 model.complete() 收到包含工具结果的完整 messages
  ├─ 无 tool_calls：返回 reply.content，结束
  └─ 有 tool_calls：继续查找、校验、执行、追加结果
     （默认最多 6 轮模型调用，到达上限则返回停止提示）
```

这里的“允许使用”指工具已存在于当前注册表中。当前 MiniAgent 路径没有额外的用户权限检查或 `read_only` 审批逻辑。模型写出未注册函数名时，只会得到“未知工具”，程序不会查找任意同名 Python 函数执行。

## 用一次计算观察 messages

第一次模型调用前，messages 有两条：system 指令和 user 问题。工具定义通过 `tools=` 单独传入，不是 messages 中的一条消息。

模型请求计算后，MiniAgent 将下面两条消息依次追加到历史中（示意）：

```json
[
  {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "id": "call_demo_1",
        "type": "function",
        "function": {
          "name": "calculator",
          "arguments": "{\"expression\": \"12 * 8\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_demo_1",
    "content": "{\"ok\":true,\"content\":96.0,\"error\":null}"
  }
]
```

第二次模型调用时，历史顺序为 system → user → assistant（请求工具）→ tool（工具结果）。模型据此可以回答“12 × 8 = 96”，也可以继续请求工具。

- `name` 决定执行哪个工具；`id` 标识这一次调用，同一工具可以被调用多次。
- `tool_call_id` 把结果关联到前面的那一次调用。
- 内部 `ToolCall.arguments` 是 Python 字典；消息里的 `function.arguments` 是 JSON 字符串。
- 内部结果是 `ToolResult` 对象；工具消息的 `content` 是其 JSON 字符串。
- 一轮返回多个工具调用时，当前代码使用 `for` 加逐个 `await` 顺序执行。

## 三种失败在哪里处理

| 情况 | 处理位置 | 返回给 MiniAgent 的结果 |
|---|---|---|
| 请求 unknown_tool | `ToolRegistry.invoke()` 查找失败 | `ok=False`，`error="未知工具: unknown_tool"` |
| calculator 缺少 expression | `Tool._validate_required()` 抛出异常，由 `ToolRegistry.invoke()` 捕获 | `ok=False`，`error="缺少必要参数: expression"` |
| calculator 计算 1 / 0 | handler 抛出异常，由 `Tool.invoke()` 捕获 | `ok=False`，error 包含 `ZeroDivisionError` |

上述失败也会序列化为 role=tool 消息，交给下一轮模型读取。失败结果不保证模型会成功修正。

`_validate_required()` 在 `Tool.invoke()` 的 try 外面，因此直接调用 `tool.invoke()` 时，校验失败会抛异常；走 `registry.invoke()` 才会将这种异常转换为 ToolResult。

## 当前实现的边界

1. 参数校验只检查 dict 类型和必填键是否存在，没有完整执行 JSON Schema 的字段类型与 `additionalProperties` 约束。Schema 写了 string，不等于本地已经验证了 string。
2. `ToolResult` 的 Pydantic 校验针对结果对象结构，不会替代输入参数校验。
3. `Tool.invoke()` 支持普通返回值和可等待返回值，但同步 handler 仍直接在当前线程执行。
4. MiniAgent 的默认 6 步指最多 6 次模型调用，不是最多 6 次工具执行；最后一轮若仍请求工具，其结果追加后可能没有下一轮模型读取。
5. 当前 `_emit()` 只发出模型调用、工具调用和取消事件，没有逐项记录完整 messages 或 ToolResult。本篇是学习日志中的链路图，不代表程序已输出完整运行轨迹。

源码定位：`src/research_agent/tools.py`；`src/research_agent/mini_agent.py` 的 30–75 行；`src/research_agent/llm.py` 的 `_normalize()`；`src/research_agent/models.py` 的 `ToolCall`。

## 阶段三：三类 JSON 的字段来源与使用者

以下保存的是教学示例，并非 API 实测响应。三者方向分别为：程序 → 模型（工具定义）；模型接口 → 程序（调用请求）；程序 → 模型（执行结果）。协议规定外层字段名和结构，开发者定义工具名称、参数及结果格式，模型根据问题生成某次调用的选择和参数值。

### 1. 工具定义：告诉模型有什么工具、如何填写参数

```json
{
  "type": "function",
  "function": {
    "name": "calculator",
    "description": "计算只包含数字、括号和基本运算符的算术表达式",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {"type": "string"}
      },
      "required": ["expression"],
      "additionalProperties": false
    }
  }
}
```

| 字段路径 | 来自哪里 | 由谁使用、用于什么 |
|---|---|---|
| `type` | `as_model_tool()` 写入固定值 `function` | 模型接口识别工具种类。 |
| `function` | `as_model_tool()` 构造的协议容器 | 模型接口读取内部工具定义。 |
| `function.name` | 开发者在 `builtin_registry()` 中写的 `calculator`，保存为 `Tool.name` | 模型据此生成调用名称；本地 Registry 也用同一个名称建立查找表。 |
| `function.description` | 开发者写的说明，保存为 `Tool.description` | 模型理解用途，决定是否选择该工具。 |
| `function.parameters` | 开发者写的参数 Schema，保存为 `Tool.parameters` | 发给模型作为参数格式说明；本地 Tool 当前只读取其中的 `required` 规则。 |
| `function.parameters.type` | 开发者声明 `object` | 告诉模型参数整体应是对象；本地通过独立的 `isinstance(arguments, dict)` 检查，并未读取这个 type 值。 |
| `function.parameters.properties` | 开发者定义的字段集合 | 告诉模型有哪些参数字段。 |
| `function.parameters.properties.expression` | 开发者自定义参数名 `expression` 及其规则 | 模型生成同名键；handler 用 `args["expression"]` 取值。这不是协议固定字段名。 |
| `function.parameters.properties.expression.type` | 开发者声明 `string` | 告诉模型 expression 应为字符串；当前本地校验未执行此类型约束。 |
| `function.parameters.required` | 开发者指定 `["expression"]` | 模型应提供该键；`_validate_required()` 实际读取列表并检查键是否存在。 |
| `function.parameters.additionalProperties` | 开发者声明 `false` | 告诉模型不要增加未声明字段；当前本地校验未执行此约束。 |

这整个对象是请求体 `tools` 数组中的一项。`definitions()` 汇总它们，`MiniAgent` 传给 `model.complete()`，真实客户端将其放入请求 payload。Schema 是格式说明，本项目没有据此实现完整校验，不能把发送定义等同于严格约束已经生效。

### 2. 调用请求：模型选择某工具，并提供这一次的参数

```json
{
  "id": "call_demo_1",
  "type": "function",
  "function": {
    "name": "calculator",
    "arguments": "{\"expression\":\"12 * 8\"}"
  }
}
```

| 字段路径 | 来自哪里 | 由谁使用、用于什么 |
|---|---|---|
| `id` | 模型接口响应携带的调用 ID；此处为教学示例值 | `_normalize()` 保存到 `ToolCall.id`；MiniAgent 将其复制到结果的 `tool_call_id`，供接口及模型上下文关联请求与结果。当前客户端在响应缺少 id 时用 `call-0` 等值兜底。 |
| `type` | 模型接口按协议返回 `function` | 标识调用类型。当前 `_normalize()` 没有读取或校验它；MiniAgent 回写 assistant 历史时固定写入 `function`。 |
| `function` | 模型接口返回的协议容器 | `_normalize()` 从这里取出 name 和 arguments。 |
| `function.name` | 模型选择要调用的工具名称 | `_normalize()` 保存到 `ToolCall.name`；`Registry.invoke()` 用它查 `_tools`，只执行已注册工具。 |
| `function.arguments` | 模型生成的本次参数，以 JSON 字符串返回 | `_normalize()` 用 `json.loads()` 转成字典，保存到 `ToolCall.arguments`，再传入 Registry、Tool、handler。 |
| 解码后的 `expression` 键 | 模型根据工具定义填写 | 必填检查确认该键存在；handler 按这个名称取值。 |
| 解码后的 `expression` 值 | 模型根据用户问题生成的 `12 * 8` | handler 交给 `safe_calculate()` 实际计算；不是开发者在 Schema 中预设的值。 |

这整个对象是响应 `choices[0].message.tool_calls` 数组中的一项。它是执行请求，不是执行结果。MiniAgent 在执行前还会将请求保存为一条 `role="assistant"` 消息中的 `tool_calls`，以保留完整历史。

### 3. 工具消息：程序将执行结果回传给模型

```json
{
  "role": "tool",
  "tool_call_id": "call_demo_1",
  "content": "{\"ok\":true,\"content\":96.0,\"error\":null}"
}
```

| 字段路径 | 来自哪里 | 由谁使用、用于什么 |
|---|---|---|
| 外层 `role` | MiniAgent 固定写入 `tool` | 模型接口据此识别这条消息是工具返回。 |
| 外层 `tool_call_id` | MiniAgent 从原来的 `call.id` 复制 | 接口及模型上下文将本结果关联到前面的那一次调用；不是工具名。 |
| 外层 `content` | MiniAgent 调用 `result.model_dump_json()` 生成的字符串 | 下一轮模型读取并理解结果；该字符串整体承载应用自定义的结果对象。 |
| content 解码后的 `ok` | `Tool.invoke()` 成功时填 True，执行失败时填 False；Registry 在未知工具或参数校验失败时也填 False | 模型据此判断工具成功与否。MiniAgent 当前不根据 ok 分支，统一追加结果。 |
| content 解码后的 `content` | 成功时取 handler 的返回值，此例为 `96.0`；失败时通常为默认 None | 模型用于生成回答或后续工具参数。 |
| content 解码后的 `error` | 执行器在失败时填写错误文字，成功时采用默认 None | 模型读取失败原因，可能尝试修正参数；成功时序列化为 `null`。 |

外层 `role/tool_call_id/content` 属于消息协议结构；字符串里面的 `ok/content/error` 是本项目用 ToolResult 定义的应用结果格式，并不是工具协议强制要求的三个字段。两个 content 同名但层级不同：外层装整份结果字符串，内层装实际业务结果。

### 字符串、字典与转义

```text
接口返回 arguments：JSON 字符串 '{"expression":"12 * 8"}'
  → json.loads()
内部 ToolCall.arguments：Python 字典 {"expression": "12 * 8"}
  → handler 执行
内部 ToolResult：ok=True, content=96.0, error=None
  → model_dump_json()
工具消息 content：JSON 字符串 '{"ok":true,"content":96.0,"error":null}'
```

当这些字符串再次放在外层 JSON 中展示时，内部双引号需要写成 `\"`，因此看起来出现许多反斜杠。这是 JSON 字符串转义，不是表达式里真的多了反斜杠。内部参数保留为字典便于代码取值；消息中的 arguments 和 content 则按当前接口使用字符串。

### 为什么普通 content 提到 calculator 不会调用工具

`MiniAgent` 判断的是 `reply.tool_calls`。如果只有 `reply.content="我要用 calculator 计算"` 而没有结构化调用列表，代码会直接返回这段文本，不执行工具。只有结构化 `tool_calls` 进入解析、查找和执行链路；名称还必须在注册表中存在。
