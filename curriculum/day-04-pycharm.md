# Day 04：Function Calling 与工具系统——PyCharm 详细学习计划

> 项目：`E:\agent_project\agent-learning-lab`  
> 环境：PyCharm + 项目 `.venv` 中的 Python 3.11  
> 投入：每天合计 8 小时，各阶段弹性安排  
> 主线：认识工具 → 直接调用 → 校验参数 → 新增工具 → 跑通模型与工具循环 → 测试与复盘

## 1. 今天的目标

今天要把“模型调用工具”这句话拆开，弄清每一步究竟由谁完成。

例如用户问：“请计算 12 × 8。”程序先把计算器的名称、用途和参数格式告诉模型。模型返回“我要调用 calculator，参数是 expression=12*8”。Python 查找这个工具、检查参数并执行计算，再把结果作为消息交给模型，模型才生成最终回答。

**模型生成调用请求，程序负责校验、执行和回传结果。** 模型不能因为写出了一个函数名，就获得执行任意 Python 函数的权限。

前几天的知识会在今天连接起来：

| 已学内容 | 今天在哪里使用 |
|---|---|
| Day 01：messages、模型请求 | 把工具说明发给模型，把工具结果发回模型 |
| Day 02：JSON、Pydantic、错误处理 | 解析工具参数、执行前校验、返回统一错误 |
| Day 03：await、协程、取消 | 执行异步工具，理解顺序依赖和资源清理 |

今天的范围是当前手写 MiniAgent。MCP、LangGraph 和完整研究流程按后续课程推进。

## 2. 弹性安排与成果

每个阶段按“预测 → 操作 → 观察 → 解释 → 验收”进行。不规定理论或编码必须占多少小时。

- 核心任务优先；陌生概念不清楚时先补理解，再编码。
- 每完成一小项就运行相关测试。
- 提前完成核心任务，再做文末扩展。
- 8 小时结束仍有未完成核心项，记录下来，下次先补齐。

今天必须留下：

- [ ] 一张工具调用完整流程图。
- [ ] 工具定义、模型调用请求、工具结果三类 JSON 示例。
- [ ] 现有三个工具的直接调用结果。
- [ ] 执行前严格校验参数的实现及测试。
- [ ] 一个自己新增的只读工具 `count_occurrences`。
- [ ] 一条离线、可重复的完整 Agent 调用轨迹。
- [ ] 最大步数能够终止反复调用的测试。
- [ ] 少量真实工具选择实验及结果记录。
- [ ] Day 04 学习日志和 Git 提交。

真实 API 暂时不可用时，可以完成其余任务，但应把真实选择实验记为待补，不能把假模型实验当成模型真实选择能力的证据。

## 3. 今天操作哪些文件

下列相对路径都从项目根目录开始。

| 文件 | 操作 | 用途 |
|---|---|---|
| `src/research_agent/tools.py` | 核心修改 | 工具定义、注册、校验、执行、新工具 |
| `src/research_agent/mini_agent.py` | 阅读和断点 | 模型—工具循环、消息追加、最大步数 |
| `src/research_agent/llm.py` | 阅读 | tools 如何发送、arguments 如何解析 |
| `src/research_agent/models.py` | 阅读 | `ToolCall`、`ModelReply`、`Usage` |
| `src/research_agent/demo_model.py` | 阅读 | 理解离线演示的限制 |
| `examples/day04_tool_lab.py` | 新建 | 不调用模型，直接实验工具 |
| `examples/day04_agent_trace.py` | 新建 | 输出完整工具调用轨迹 |
| `tests/test_tools.py` | 补充 | 校验、新工具、失败处理 |
| `tests/test_mini_agent.py` | 补充 | 消息关联、工具失败、循环终止 |
| `curriculum/day-04-log.md` | 新建 | 图、JSON、预测、结果和复盘 |

不要用教程整段覆盖已有文件。先阅读当前内容，再逐项修改，保留已经完成的练习。

## 4. 开始前：确认学习起点

在 PyCharm 打开项目，Terminal 执行：

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest tests/test_tools.py tests/test_mini_agent.py -q
```

保存实际测试结果；不要预先填写通过数量，也不要求与其他人的数量相同。

前置自查：

- [ ] 能解释 JSON 字符串和 Python 字典的区别。
- [ ] 能解释 Pydantic 校验成功后会得到什么。
- [ ] 知道普通异常与 `asyncio.CancelledError` 的区别。
- [ ] 能说出为什么后续步骤可能必须等待前一步结果。

截至本计划编写时，项目工具代码有以下教学起点：

1. `Tool` 保存名称、描述、参数 Schema 和处理函数。
2. `_validate_required()` 只检查对象类型和必填字段，不是完整参数校验。
3. `calculator` 与 `text_statistics` 会用 `str(...)` 转换输入，可能掩盖错误类型。
4. `read_only` 只是保存的属性，当前没有权限检查逻辑使用它。
5. `DemoModel` 只按正则规则选择计算器，不能自动理解你新增工具的描述。
6. `MiniAgent` 默认最多进行 6 轮模型循环。

如果你已修改过其中某项，以当前文件为准，先检查并记录差异。

## 5. 阶段一：画清模型和程序的边界

阅读 `tools.py`，按下面顺序追踪：

```text
ToolResult
→ Tool.__init__()
→ Tool.as_model_tool()
→ Tool.invoke()
→ ToolRegistry.register()
→ ToolRegistry.definitions()
→ ToolRegistry.invoke()
→ builtin_registry()
```

在日志画出这条链路：

```text
用户问题
  ↓
MiniAgent 组装 messages + 工具定义
  ↓
模型返回 ToolCall(name, arguments, id)
  ↓
ToolRegistry 按 name 查找允许使用的工具
  ↓
Tool 校验 arguments
  ↓
Python handler 执行操作
  ↓
ToolResult(ok, content, error)
  ↓
追加 role=tool 的消息，与 tool_call_id 关联
  ↓
模型读取结果，回答或继续请求工具
```

### 必须理解的四个概念

| 概念 | 在项目中是什么 | 不应混淆的地方 |
|---|---|---|
| 工具定义 | 发给模型的名称、描述、参数格式 | 里面没有 Python handler 的可执行代码 |
| 工具调用请求 | 模型返回的名称、参数、调用 ID | 此时函数尚未执行 |
| 工具执行器 | Registry + Tool + handler | 真正查找、校验并运行函数 |
| 工具结果 | 函数成功或失败的信息 | 还需要放回消息才能供模型使用 |

Function Calling 的基本流程可对照 [DeepSeek Tool Calls 官方说明](https://api-docs.deepseek.com/guides/tool_calls/)。今天以项目现有 Chat Completions 消息结构练习，不混用其他 API 的消息字段。

**检查点：**不看代码，解释为什么模型返回一个未注册工具名时，程序应报告“未知工具”，不能尝试执行同名任意函数。

## 6. 阶段二：先绕过模型，直接调用工具

在 PyCharm 中右键 `examples` → 新建 Python 文件 → `day04_tool_lab.py`。

先输入这个最小实验：

```python
import asyncio
import json

from research_agent.tools import builtin_registry


async def main():
    registry = builtin_registry()
    print(json.dumps(registry.definitions(), ensure_ascii=False, indent=2))

    cases = [
        ("calculator", {"expression": "12 * 8"}),
        ("current_time", {}),
        ("text_statistics", {"text": "hello agent"}),
        ("calculator", {}),
        ("unknown_tool", {}),
        ("calculator", {"expression": "1 / 0"}),
    ]

    for name, arguments in cases:
        result = await registry.invoke(name, arguments)
        print(name, result.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
```

创建运行配置：

| 配置项 | 内容 |
|---|---|
| 名称 | `Day04 Tool Lab` |
| 脚本路径 | `E:\agent_project\agent-learning-lab\examples\day04_tool_lab.py` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | `E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe` |

每次运行前先预测，再核对：

| 输入 | 预期 |
|---|---|
| `12 * 8` | `ok=True`，结果 96 或 96.0 |
| 当前时间 | UTC 时间字符串；不要断言某个固定时刻 |
| `hello agent` | 字符数 11、非空白字符数 10、空白分词数 2 |
| 计算器缺参数 | `ok=False`，明确指出缺参 |
| 未注册工具 | `ok=False`，未知工具 |
| `1 / 0` | `ok=False`，执行错误；下一案例仍能运行 |

注意 `text_statistics` 的 words 是按空白切分的数量，不是中文分词结果，也不是模型 Token 数量。

**检查点：**这些调用没有经过模型。它们证明工具执行器能工作，但不能证明模型能选对工具。

## 7. 阶段三：读懂工具 Schema 与三类 JSON

### 7.1 工具定义

以计算器为例：

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

解释：`properties` 描述字段，`required` 指定必填字段，`additionalProperties: false` 禁止未声明字段。只把字段写进 properties 并不自动使它必填。参考 [JSON Schema 对象说明](https://json-schema.org/understanding-json-schema/reference/object)。

### 7.2 模型返回的调用请求

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

外层是 JSON 对象，`arguments` 的值在这个协议里又是一个 JSON 字符串。`llm.py` 的 `_normalize()` 会把它解析成 `ToolCall.arguments` 字典。

### 7.3 Python 返回给模型的工具消息

```json
{
  "role": "tool",
  "tool_call_id": "call_demo_1",
  "content": "{\"ok\":true,\"content\":96.0,\"error\":null}"
}
```

工具消息之前，消息历史必须保留模型发出的 assistant 工具调用消息。不要只追加结果而丢弃原来的调用请求。

`tool_call_id` 匹配一次调用；工具名匹配一种功能。同一工具调用两次，仍需要分别关联结果。

### 日志练习

保存以上三类 JSON，标注每个字段来自哪里、由谁使用。再解释为什么 `content` 中出现单词 calculator，并不等于真的发出了工具调用：必须检查结构化的 `tool_calls`。

## 8. 阶段四：暴露当前参数校验的缺口

在直接调用实验中加入：

```python
("calculator", {"expression": 123}),
("calculator", {"expression": "1+1", "unexpected": True}),
("current_time", {"timezone": "Asia/Shanghai"}),
("text_statistics", {"text": [1, 2, 3]}),
```

先预测应该拒绝哪些，再看当前代码实际做了什么。

你应发现：Schema 虽然声明了类型和额外字段限制，但 `_validate_required()` 并没有执行这些规则。`str(...)` 还会把错误类型变成字符串，使操作看起来成功。

今天必须修复的契约：

1. 参数必须为对象。
2. 必填字段不能缺失。
3. 字段类型必须符合要求。
4. 未声明字段不得进入 handler。
5. 新工具的长度、空字符串等业务约束得到校验。
6. 校验失败必须在 handler 执行之前返回明确错误。

**Schema 是说明；运行时校验必须由代码实际执行。** 即使供应商提供严格输出功能，本地输入校验仍然是执行入口的一部分。

## 9. 阶段五：用 Pydantic 实现执行前校验

沿用 Day 02 学过的 Pydantic，不必今天手写完整 JSON Schema 验证器。

### 9.1 定义输入模型

在 `tools.py` 中新增模型，例如：

```python
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictToolArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CalculatorArgs(StrictToolArgs):
    expression: str = Field(min_length=1, max_length=100)


class CurrentTimeArgs(StrictToolArgs):
    pass


class TextStatisticsArgs(StrictToolArgs):
    text: str = Field(max_length=10000)
```

10,000 字符是本练习选择的本地输入上限，不是供应商标准。空文本在统计工具中可以合法，预期各统计值为 0。

`strict=True` 控制类型转换，`extra="forbid"` 拒绝额外字段。两者作用不同。类型的具体严格行为以 Pydantic 为准，参见 [严格模式说明](https://docs.pydantic.dev/latest/concepts/strict_mode/)。

### 9.2 修改 Tool 接口，保持现有调用可用

建议给 `Tool.__init__()` 增加可选参数：

```python
input_model: type[BaseModel] | None = None
```

按以下顺序实现：

1. 保存 `self.input_model`。
2. 有输入模型时，用其 `model_json_schema()` 生成 `self.parameters`，作为发给模型的 Schema。
3. 没有输入模型时，保留已有 `parameters` 与必填字段检查，兼容旧构造方式；不要声称旧路径已有完整校验。
4. 让所有三个内置工具及今天的新工具都绑定输入模型。
5. 在 `Tool.invoke()` 中，先验证参数是字典，再调用输入模型的 `model_validate(arguments)`。
6. 将通过校验的对象 `model_dump()` 为字典，交给现有 handler。
7. 捕获 `ValidationError`，转换成 `ToolResult(ok=False, error=...)`，不要继续执行 handler。
8. 从已校验的 handler 中移除不必要的 `str(...)`，避免掩盖错误。

可继续保留 `parameters` 参数，将内置工具的值改为对应模型生成的 Schema；重点是同一输入模型同时驱动对外描述和本地校验，避免两套规则不同步。

### 9.3 明确异常边界

建议对外调用 `registry.invoke(...)` 时都返回 `ToolResult`：未知工具、校验失败、执行错误分别有明确消息。

注意原代码 `_validate_required()` 在 try 外面，缺参异常由 Registry 捕获。调整时要决定在哪一层转换错误，并写测试，避免遗漏新的 `ValidationError`。

如需继续兼容现有测试的“缺少必要参数”提示，可以保留必填检查；或明确更新错误契约及测试。不要只为让测试变绿删除对错误类型与 handler 未执行的验证。

只输出错误字段、错误类别和说明即可；不需要把整份用户输入拼进错误文本。取消应继续传播，不要用 `except BaseException` 把它转换成普通工具失败。

### 9.4 用计数器证明先校验后执行

在测试中定义 handler，每调用一次就让计数加一。先传入非法参数，断言：

```text
result.ok 为 False
调用计数仍为 0
```

再传合法参数，断言调用计数为 1。

**检查点：**这比“报了一次错”更有说服力，因为它证明非法输入没有进入真实操作。

## 10. 阶段六：新增 count_occurrences 工具

工具需求：在文本中查找指定子串，返回非重叠出现次数，默认区分大小写。它只操作传入文本，不读写文件。

### 10.1 输入模型

```python
class CountOccurrencesArgs(StrictToolArgs):
    text: str = Field(max_length=10000)
    needle: str = Field(min_length=1, max_length=200)
    case_sensitive: bool = True
```

约定：

- 空 text 合法，结果为 0。
- 空 needle 非法，避免产生难理解的统计结果。
- `case_sensitive=False` 时，先对两端使用 `casefold()`，再比较；它是这里明确选择的匹配规则。
- 本工具统计子串，不是单词数、Token 数，也不处理正则表达式。

### 10.2 写处理函数

```python
def count_occurrences(arguments: dict) -> dict:
    text = arguments["text"]
    needle = arguments["needle"]
    if not arguments["case_sensitive"]:
        text = text.casefold()
        needle = needle.casefold()
    return {"count": text.count(needle)}
```

默认值应由输入模型校验后补齐，因此 handler 从校验后的字典读取 `case_sensitive`。

### 10.3 注册

在 `builtin_registry()` 中追加 Tool，设置：

- 名称：`count_occurrences`。
- 描述：`统计给定文本中指定子串的非重叠出现次数。默认区分大小写，可设置 case_sensitive=false 忽略大小写；不做正则匹配。`
- 参数 Schema：由 `CountOccurrencesArgs` 生成。
- 输入模型：`CountOccurrencesArgs`。
- handler：上面的处理函数。
- read_only：`True`。

通过 `registry.definitions()` 确认新工具确实出现在发给模型的列表中。

### 10.4 最少测试案例

| text | needle | case_sensitive | 预期 |
|---|---|---|---|
| `agent agent` | `agent` | 默认 | 2 |
| `Agent agent AGENT` | `agent` | True | 1 |
| `Agent agent AGENT` | `agent` | False | 3 |
| `banana` | `ana` | True | 1，非重叠 |
| 空字符串 | `agent` | 默认 | 0 |
| `abc` | 空字符串 | 默认 | 校验失败 |
| `abc` | `a` | 字符串 `"false"` | 严格类型校验失败 |

这一步的测试直接调用 Registry，不消耗 API。

## 11. 阶段七：在 PyCharm 中观察完整循环

### 11.1 先调试现有计算器 Demo

建立 Python 模块运行配置：

| 项目 | 值 |
|---|---|
| 名称 | `Day04 Calculator Trace` |
| 模块名称 | `research_agent.cli` |
| 参数 | `demo "计算 12 * 8"` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | 项目 `.venv` |

依次设置断点，用语句定位而不依赖可能变化的行号：

1. `MiniAgent.run()`：`self.model.complete(...)`。
2. `ToolRegistry.invoke()`：从 `_tools` 查找工具。
3. `Tool.invoke()`：参数验证之后、调用 handler 之前。
4. `MiniAgent.run()`：把 `role="tool"` 消息加入 messages。
5. `MiniAgent.run()`：没有 `reply.tool_calls` 时返回最终文本。

记录两次模型调用前的 messages 差别。第二次应包含第一次 assistant 工具请求及对应 tool 结果。

### 11.2 为新工具建立可控离线模型

`DemoModel` 不会因为注册了新工具就自动学会选择它。新建 `examples/day04_agent_trace.py`，在这个实验文件中写一个专用假模型，不要把规则硬塞进生产 Agent。

假模型参考：

```python
import json

from research_agent.models import ModelReply, ToolCall, Usage


class CountDemoModel:
    async def complete(self, messages, *, tools=None, response_format=None):
        usage = Usage(model_calls=1)
        if messages[-1]["role"] == "user":
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id="count-demo-1",
                        name="count_occurrences",
                        arguments={"text": "agent agent", "needle": "agent"},
                    )
                ],
                usage=usage,
            )
        if messages[-1]["role"] == "tool":
            payload = json.loads(messages[-1]["content"])
            if not payload["ok"]:
                return ModelReply(content="工具失败：" + payload["error"], usage=usage)
            return ModelReply(
                content=f"子串出现 {payload['content']['count']} 次。",
                usage=usage,
            )
        raise AssertionError("出现了本实验未预期的消息状态")
```

为它补上主程序：构造 `MiniAgent(CountDemoModel(), builtin_registry())`，调用 `.run(...)`，打印最终回答和调用次数。沿用 Day 03 的 `asyncio.run(main())` 入口。

可以提供 `on_event` 异步回调，打印 `event.kind` 与 `event.message`。现有事件只能看到模型/工具调用摘要，完整消息需通过断点查看或在假模型中保存 messages 的深拷贝。

预期：回答包含“2 次”，工具调用 1 次、模型调用 2 次。假模型不产生真实 Token 账单，不能把模拟用量当作计费数据。

**检查点：**离线模型验证程序流程，真实模型实验验证工具选择；两类证据要区分。

## 12. 阶段八：验证错误路径与停止条件

扩展 `tests/test_tools.py`、`tests/test_mini_agent.py`。下面是测试行为，不要求照搬函数命名：

| 测试 | 必须证明什么 |
|---|---|
| 正常计算、时间、文本统计 | 原有功能仍然工作 |
| 缺参、错类型、额外字段 | 返回清楚错误，handler 计数为 0 |
| 未知工具 | 不执行任何已注册 handler |
| 处理函数抛异常 | 转成失败结果，下一次调用仍可成功 |
| 新工具正确输入 | 统计符合非重叠、大小写约定 |
| 新工具非法输入 | 在执行前拒绝 |
| 同步与异步 handler | 返回真正的执行结果，没有未等待协程 |
| 普通问题无需工具 | 直接给答案，tool_calls 为 0 |
| 模型调用后收到工具结果 | call ID 对应，结果内容完整 |
| 工具失败后再次调用模型 | 模型收到 `ok=False`，没有冒充成功结果 |
| 重复工具名注册 | 明确拒绝，不能静默覆盖 |
| 模型持续请求工具 | 最大步数到达后终止 |

### 最大步数实验

写一个每次 `complete()` 都返回计算器调用的假模型；每轮生成不同调用 ID。构造 `MiniAgent(..., max_steps=3)`。

在每次调用都能返回的前提下，应观察到：

- 模型最多调用 3 轮。
- 每轮一个工具时工具执行 3 次。
- 最终得到“达到最大步骤数”的停止信息。

`max_steps` 限制循环轮数，不保证总耗时；某个工具永远不返回时仍可能卡住。也不要把它当成严格的工具调用总量上限，因为一个模型回复可能包含多个调用。

### 当前工具执行能力的边界

- `safe_calculate()` 使用受限 AST 解析，理解它允许哪些节点即可，不要改成 `eval()`。
- 当前 AST 检查不是通用 Python 沙箱，也不代表任意算术都具备完善的资源预算。
- `read_only=True` 只是标签；要阻止写操作必须在执行器中实现策略。今天新增的是纯文本工具。
- 现有同步 handler 在事件循环线程内直接执行；把慢同步函数放在 async 包装器里不会自动变成非阻塞。

**检查点：**能区分“有限轮数”和“有总超时”，不会把工具属性误认为实际权限控制。

## 13. 阶段九：少量真实模型工具选择实验

先完成离线校验、结果回传和错误路径，再用真实 API。

从现有运行配置复制一个 Python 模块配置：

```text
模块名称：research_agent.cli
参数：ask "请调用文本统计工具统计 hello agent 的字符数。"
工作目录：E:\agent_project\agent-learning-lab
解释器：项目 .venv
```

继续使用 `.env` 中已能工作的模型配置。API Key 不写进脚本或学习日志。模型与接口能力以实际服务支持为准，不为本课随意更换环境。

建议选以下 3～4 个问题做人工小样本观察：

| 问题 | 预期工具 | 观察项 |
|---|---|---|
| 请调用计算器计算 `(12 + 3) * 2` | calculator | 参数为表达式，结果 30 |
| 请调用工具获取当前 UTC 时间 | current_time | 参数为空对象，明确 UTC |
| 请调用工具统计 `hello agent` 的字符数 | text_statistics | text 完整，字符数 11 |
| 请调用工具统计 `Agent agent AGENT` 中 agent 的次数，忽略大小写 | count_occurrences | case_sensitive 为布尔 False，结果 3 |

当前客户端使用 `tool_choice="auto"`，不保证每次都选工具。**答案正确不等于发生了工具调用。** 通过断点或执行轨迹确认工具名称与参数，再记录最终回答。

单个问题通常需要工具前后多次模型请求，费用按实际请求累计。保存模型请求次数、Token 和结果，不要把“4 个问题”误记为“4 次模型调用”。

如果没选对工具：先检查 `registry.definitions()` 是否包含新工具，再检查描述与问题是否明确、Schema 与参数是否一致。分析一次失败比反复重试更有学习价值。

描述对比可作为扩展：将“处理文本”改成具体用途说明，对同一问题观察差异。少量结果只算观察，不能据此声称准确率已经显著提高。

## 14. 验证与回归

先运行目标测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tools.py tests/test_mini_agent.py -q
```

再检查客户端兼容性：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tools.py tests/test_mini_agent.py tests/test_llm.py -q
```

如果今天只修改文中这些文件，相关回归通过后即可整理交付；若修改波及其他模块，再增加对应测试。

测试失败时分类处理：

| 现象 | 先检查 |
|---|---|
| 参数明明有 Schema 仍被接受 | 是否真的绑定并调用了 input_model |
| handler 提示缺少默认字段 | 是否用了校验后 model_dump 的字典 |
| 新工具不出现在 definitions | 是否追加到 builtin_registry |
| Demo 没选新工具 | 是否误用仅支持计算器规则的 DemoModel |
| 模型收到工具结果报协议错误 | assistant 调用消息是否保留、ID 是否匹配 |
| 出现 coroutine 未等待警告 | 异步 handler 的结果是否 await |
| 缺参测试断言失败 | 错误契约变化还是校验失效，不能仅看文字不同 |
| 模型不断调用 | 是否有最大步数及持续调用的假模型测试 |

## 15. 日志模板与 Git 提交

创建 `curriculum/day-04-log.md`，至少包含：

```markdown
# Day 04 学习日志

## 我理解的调用流程
填写流程图，并标出模型与程序的边界。

## 三类 JSON
工具定义、调用请求、结果消息；说明每个 ID 的关联。

## 参数校验
修改前哪些输入错误通过？修改后怎样证明 handler 没执行？

## 新工具
工具名、用途、字段约束、非重叠与大小写规则。

## 实验结果
| 问题 | 模型或直接调用 | 预期工具 | 实际工具 | 参数 | 结果 |
|---|---|---|---|---|---|

## 测试证据
命令、实际结果、修复过的问题。

## API 与成本
真实任务数、请求数、Token；未做真实实验则写待补。

## 我还解释不清的问题

## 下一天先补什么
```

在项目根目录检查版本状态：

```powershell
git status
git diff --check
```

若项目尚未初始化 Git，确认所在目录后 `git init`，先补可复现的项目基础提交。已有仓库直接检查本次差异。

按实际修改的文件暂存，不存在的文件从命令中去掉：

```powershell
git add src/research_agent/tools.py tests/test_tools.py tests/test_mini_agent.py examples/day04_tool_lab.py examples/day04_agent_trace.py curriculum/day-04-log.md curriculum/day-04-pycharm.md
git diff --cached --stat
git status
git commit -m "learn: validate tool inputs and trace function calls"
```

确认没有 `.env`、API Key 或整份调试凭证进入暂存区。若还有其他相关代码修改，检查后再加入提交。

## 16. 核心完成后的扩展

1. **同一轮多个工具调用：**当前 MiniAgent 已遍历多个调用，只是逐个执行。先写假模型返回两个调用，验证两个 ID 与两份结果都保留；独立且只读时再考虑受 Semaphore 限制的并发执行。
2. **异步工具超时：**用 Day 03 的模拟慢工具验证 `wait_for()`，并让取消传播。不要声称它能硬中断当前线程上的同步阻塞函数。
3. **工具描述对照：**比较模糊描述与明确描述，记录相同问题的选择差异。
4. **权限策略：**把 read_only 从标签推进为执行器检查策略，只用无副作用的模拟工具验证拒绝行为。
5. **重复注册一致性：**当前 `register()` 拒绝重复名，但构造器的字典推导会覆盖同名工具。可让构造器复用 register 并补测试。

## 17. 今日最终验收

- [ ] 能完整讲清“工具说明 → 模型请求 → 参数校验 → Python 执行 → 结果回传 → 最终回答”。
- [ ] 能区分工具名与调用 ID，并正确关联结果。
- [ ] 三个内置工具仍能直接调用。
- [ ] 缺参、错类型、额外字段和新工具业务约束在执行前被拒绝。
- [ ] 测试证明非法参数不会触发 handler。
- [ ] 新增 count_occurrences，并完成正常与异常案例。
- [ ] 假模型完整循环通过，观察到真实的工具执行和第二轮消息。
- [ ] 工具失败能回传错误，进程继续运行。
- [ ] 持续工具请求在最大步数到达时终止。
- [ ] 完成并记录少量真实模型选择实验；不可用时明确标记待补。
- [ ] 日志、测试证据、Git 提交齐全。

不要求今天完成 Day 05 的全部 15 个固定 Agent 问题；今天先保证工具层契约与代表性调用链可靠。

## 18. 口头验收题

1. 模型返回 `calculator` 后，哪段 Python 代码真正执行计算？
2. 给模型看的工具定义中，为什么没有 handler？
3. Schema 声明了 string，为什么仍需要本地校验？
4. `strict=True` 和 `extra="forbid"` 分别解决什么问题？
5. 为什么工具参数不能简单 `str(...)` 后就当作合法？
6. 同一工具调用两次，如何区分两次结果？
7. 为什么要保留 assistant 的工具调用消息？
8. 直接调用成功、假模型流程成功、真实模型选对工具分别证明什么？
9. `read_only=True` 当前是否会阻止函数写文件？为什么？
10. 最大步数为什么不能替代单次工具超时？

## 19. 按需阅读资料

- [DeepSeek：Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)：对照模型请求与结果回传。
- [JSON Schema：Object](https://json-schema.org/understanding-json-schema/reference/object)：理解字段、必填项、额外字段。
- [Pydantic：Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)：理解本地严格类型校验。

先能解释自己项目里的一个完整实例，再扩展阅读。Day 05 会把这些能力整理成 Mini Agent v0，并补齐状态、轨迹和固定测试集。
