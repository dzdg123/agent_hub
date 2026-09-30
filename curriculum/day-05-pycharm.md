# Day 05：完成 Mini Agent v0——PyCharm 详细学习计划

> 项目目录：`E:\agent_project\agent-learning-lab`
>
> 环境：PyCharm + 项目 `.venv` 中的 Python 3.11
>
> 总投入：8 小时，各阶段时间灵活调整
>
> 本周成果：一个可以回答、调用工具、记录过程，并明确停止的最小 Agent

> 2026-09-30 实施复核：工程交付及验收见 [案例表](day-05-cases.md) 和 [完成日志](day-05-log.md)。
> 第 3 节是历史起点；当前详细结果接口已实现。新增完整验收位于 `tests/test_day05_acceptance.py`，原 `tests/test_mini_agent.py` 练习保留。
> `src/research_agent/trace.py` 提供轨迹导出，完整演示为 `examples/day05_agent_v0.py`；原带下划线的文件名保留为兼容入口。
> 个人口头讲解仍需本人完成，不能用测试通过替代；第 15 节列为后续可选扩展。

## 1. 今天要完成什么

前四天分别练习了模型请求、可靠客户端、异步执行和工具系统。今天把这些能力连成一个完整、可观察、可测试的 Mini Agent v0。

你需要能回答四个问题：

1. Agent 现在进行到哪一步？
2. 它为什么调用这个工具，实际传入什么、得到什么？这里的“为什么”指用户问题、工具定义和调用选择之间的关系，不要求访问模型内部思维过程。
3. 如果模型失败、工具失败、用户取消或一直没有答案，会怎样停止？
4. 怎样证明这些行为确实发生，而不只是终端打印了一句看起来正确的回答？

**今天的验收重点是运行流程正确、有明确状态、有执行证据。** 离线假模型用来验证程序行为；它不能证明真实模型的推理或工具选择能力。

不要求今天引入 LangGraph、MCP、网页服务或数据库。现有项目包含这些后续模块，今天只处理 MiniAgent 及其直接依赖。

## 2. 弹性推进规则与交付物

当天按“最小闭环 → 错误与停止 → 轨迹 → 固定案例 → 演示与复盘”推进。读不懂某个概念时，先用小实验理解，再回来实现。

| 优先级 | 成果 | 完成依据 |
|---|---|---|
| 核心 | Agent 状态与详细结果 | 完成、失败、取消、达到步数上限可区分 |
| 核心 | 完整消息与执行轨迹 | 能追溯模型输入、工具调用、结果和终止原因 |
| 核心 | 15 个固定案例 | 每个有输入、预设行为、可执行断言和结果 |
| 核心 | 正常与异常演示 | 可以稳定重现一次成功和一次受控失败 |
| 核心 | 第一周复盘 | 用自己的话画图并讲解完整数据流 |
| 扩展 | 少量真实模型回归 | 补充观察，不替代离线行为测试 |

不把 8 小时拆成固定时段。如果核心工作未完成，保留未完成清单，下一次先补齐；不为按时收尾而删掉测试或把失败写成完成。

## 3. 依据当前代码制定的起点

以下是 2026-09-22 阅读项目代码得到的状态，不是对你已完成全部验收的推断：

- `tools.py` 已有四个绑定 Pydantic 输入模型的工具：计算器、UTC 时间、文本统计、子串计数。
- `examples/day04_agent_trace.py` 已有正常与失败实验，保存模型调用前的消息深拷贝。
- `MiniAgent.run()` 目前返回 `(answer, usage)`，状态通过文本隐含表达。
- 目前仅在每轮开始检查取消；同轮第二个工具前没有再次检查。
- 模型调用失败可能把 `LLMError` 直接抛给调用者。
- 当前事件只有模型/工具调用摘要，缺少完整结果和统一终止事件。
- 普通最终回答直接返回，没有追加到 messages。
- `max_steps` 已限制循环轮数，但达到限制时没有独立的结构化状态。

还发现两个适合先补齐的 Day 04 测试问题：

1. `test_registry_validates_missing_arguments` 仍断言错误含“缺少必要参数”，当前绑定输入模型的路径返回“参数校验失败”。先运行确认，再让断言与已选择的契约一致。
2. `test_validate_before_handeler` 当前只创建工具和计数器，没有实际调用与断言。即便它显示通过，也没有证明校验发生在执行前。

另外，`count_occurrences` 当前返回 `{"text": 2}`，假模型和测试也按 text 字段读取。今天沿用这个已一致的契约。若以后改名为 count，需要同时修改生产者与消费者，不能只改一处。

## 4. 文件操作清单

下列路径相对于项目根目录。本文出现的 `MiniAgentStatus`、`MiniAgentResult`、`run_detailed()` 是今天建议实现的新接口，当前项目尚未提供。

| 文件 | 操作 | 目的 |
|---|---|---|
| `src/research_agent/models.py` | 新增两个小模型 | MiniAgent 状态和运行结果，不改研究任务的 TaskStatus |
| `src/research_agent/mini_agent.py` | 核心修改 | 循环、状态、取消检查、错误边界、轨迹 |
| `src/research_agent/tools.py` | 阅读，按测试需要微调 | 沿用工具契约，不重写工具系统 |
| `src/research_agent/llm.py` | 阅读 | 理解客户端错误和用量来源 |
| `src/research_agent/cli.py` | 最小修改或仅回归 | 保证原有 demo/ask 仍能运行 |
| `tests/test_tools.py` | 补齐遗留测试 | 验证非法参数不会执行 handler |
| `tests/conftest.py` | 新建或追加 fixture | 可复用的脚本假模型；已有文件不覆盖 |
| `tests/test_mini_agent.py` | 扩充 | 至少 15 个固定 Agent 案例 |
| `examples/day05_agent_v0.py` | 新建 | 离线演示、控制台轨迹和结果文件 |
| `curriculum/day-05-cases.md` | 新建 | 15 个案例与测试函数对应表 |
| `curriculum/day-05-log.md` | 新建 | 测试证据和第一周复盘 |
| `.gitignore` | 追加专用输出目录 | 忽略本地调试轨迹 |

本计划只给你操作路线和示例。生产代码修改与测试练习由你在学习过程中完成。

## 5. 阶段零：建立可信的起始基线

### 5.1 在 PyCharm Terminal 中运行

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest tests/test_tools.py tests/test_mini_agent.py -q
```

记录实际失败和通过数，不沿用前几天的数字。

先修复上面两个测试问题：

- 缺参案例断言 `result.ok is False`、`result.content is None`、错误指向 expression；如果依赖某个错误文本前缀，就明确写下这个契约。
- 将校验顺序测试改成异步测试，实际传错类型和额外字段；每次失败后断言 handler 计数为 0。再传合法输入，断言结果正确且计数为 1。
- 测试 handler 的实参实际是校验后的字典，类型标注相应写成 dict，避免误写成 Pydantic 模型实例。

不要用删除断言、捕获所有错误然后 pass 的方式修复。

### 5.2 回顾一条已完成的链路

右键运行 `examples/day04_agent_trace.py`，工作目录设为项目根目录。

观察并记下：

```text
第 1 次模型输入：system + user
第 1 次模型输出：count_occurrences 调用请求
工具结果：{"text": 2}
第 2 次模型输入：system + user + assistant/tool_calls + tool
最终回答：子串出现 2 次
```

**检查点：**先确认已有基础可运行，再开始扩展。测试失败与预期不同时，先解释原因。

## 6. 阶段一：把 Agent 状态写清楚

### 6.1 选择简单的状态契约

今天使用这些状态：

| 状态 | 含义 | 是否终态 |
|---|---|---|
| running | 正在调用模型或工具 | 否 |
| completed | 模型已给出非空最终回复 | 是 |
| failed | 预期的模型服务错误或无效空回复导致无法继续 | 是 |
| cancelled | 在执行边界观察到用户取消 | 是 |
| stopped | 达到最大模型循环轮数，尚未得到最终回复 | 是 |

completed 表示本次对话流程完成，不代表用户目标一定成功。例如工具返回“找不到文件”，模型据此明确解释失败，也可以正常结束流程，但轨迹中必须保留工具失败记录。

### 6.2 建议的数据类型

在 `models.py` 中复用已有 `Usage`、`RunEvent`，新增：

```python
class MiniAgentStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"


class MiniAgentResult(BaseModel):
    run_id: str
    status: MiniAgentStatus = MiniAgentStatus.RUNNING
    answer: str = ""
    stop_reason: str | None = None
    steps: int = 0
    messages: list[dict[str, Any]] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    elapsed_seconds: float = 0.0
```

将新类放在引用类型已经定义之后。`StrEnum`、`BaseModel`、`Field`、`Any` 在当前文件中已有导入。

注意：

- `messages` 保存本次完整对话；每轮输入快照放在 events 中。
- `default_factory` 为每次运行创建独立容器。
- `steps` 表示已开始的模型循环次数。
- `elapsed_seconds` 是整个 Agent 的墙钟耗时；不要与当前 Usage 中累计的模型调用耗时混为一谈。
- 不修改后续研究工作流用的 `TaskStatus`、`ResearchState`。

### 6.3 保留旧入口，避免影响此前练习

建议把实际循环迁移到：

```python
async def run_detailed(
    self,
    prompt: str,
    *,
    run_id: str | None = None,
    on_event: EventCallback | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> MiniAgentResult:
    ...
```

这里的 `...` 是你需要实现的位置。

原 `run()` 保留现有签名和二元组返回方式，只调用 `run_detailed()` 后返回 `result.answer, result.usage`。不要把同一套循环复制两份。

未传 run_id 时可用 `uuid.uuid4().hex` 生成；教学导出文件使用这个内部生成的 ID。每次调用都创建新的结果对象，不把 messages 或 Usage 作为会积累内容的实例共享状态。

**检查点：**旧 Day 04 脚本仍能解包 `(answer, usage)`，新演示能读取详细状态。

## 7. 阶段二：逐步改造循环

按下面顺序做，每完成一个分支就跑一个对应测试。

### 7.1 正常开始与普通回答

1. 检查 `max_steps >= 1`，非法设置直接抛 ValueError；不要进入零轮循环。
2. 创建本次运行对象，初始化 system 和 user 消息。
3. 记录开始事件与开始计时。
4. 检查取消，再开始一次模型调用。
5. 收到回复后记录模型输出、请求 ID 和用量。
6. 如果没有工具调用且 content 非空，追加最终 assistant 消息，标记 completed，返回结果。
7. 如果既没有工具调用，又只有空白 content，标记 failed，原因设为 `empty_response`。这是本教学项目今天选择的策略。

模型有工具调用而 content 为空，是合法情况，不能被空回复分支误伤。

### 7.2 工具循环

继续复用现有协议顺序：

```text
保存 assistant 工具调用消息
→ 逐个检查取消
→ 查找、校验、调用工具
→ 保存 ToolResult
→ 追加对应 tool 消息
→ 下一轮模型读取结果
```

同一轮多个工具仍按顺序执行。每份结果都必须关联原来的 call.id。今天无需引入并行工具执行。

工具正常返回 `ok=False` 时也作为工具消息回传，让模型有机会说明失败或提出可修复的参数。不要把它当成程序崩溃，也不要悄悄改成成功。

### 7.3 模型失败

在调用 `self.model.complete()` 的边界捕获项目的 `LLMError`：

- 保存错误类别和简短说明。
- 标记 failed，停止本次运行。
- 不再触发工具调用或新的模型调用。

有限网络重试由 Day 02 的客户端负责；不要在 Agent 外层再套一个无上限重试循环。

不要把包围整个程序的 `except Exception: return "失败"` 当成可靠性实现。断言错误、拼写错误等开发问题应在测试时暴露，而不是被隐藏成普通服务故障。

### 7.4 步数耗尽

本课沿用现有行为：最多调用模型 max_steps 轮；最后一轮提出的工具请求仍按正常流程执行。如果这些工具完成后没有剩余模型轮数，就标记 stopped，原因 `max_steps`。

例如 `max_steps=3`，假模型每轮都请求一个工具：预期 3 次模型调用、3 次工具请求，最后为 stopped。最后一次工具结果已保存，但没有下一次模型读取；日志要明确这一点。

这不是“任务完成”，也不是无限继续的理由。最大步数限制模型轮数，不限制单个请求时长，也不等同于工具调用总量上限。

### 7.5 统一完成收尾

完成、失败、取消、达到上限都要经过一致的收尾逻辑：设置状态、原因、耗时，并记录一次终止事件。

选择容易理解的实现即可，例如一个小的 finish 辅助函数。不要为了状态管理引入新框架。

**检查点：**每条运行路径都有明确去向，终止后的状态不再变回 running。

## 8. 阶段三：让取消在正确位置生效

保留现有 `is_cancelled()` 回调，今天先实现边界检查式取消。

至少在以下位置检查：

1. 开始运行后、第一次模型调用之前。
2. 每轮模型调用之前。
3. 模型返回并记录已有结果之后、准备启动工具之前。
4. 每个工具执行之前。
5. 工具执行结束并记录已有结果之后、继续下一项之前。

若这些位置之前存在 `await on_event(...)`，应在事件回调返回后、真正发起新模型或工具调用前再次检查，避免回调期间已取消却仍启动操作。

一旦观察到取消，返回 cancelled，`stop_reason="user_cancelled"`，兼容旧入口的 answer 可保留“任务已取消”。已经完成的用量与工具结果仍要保存。

### 必须做的两个实验

**实验 A：开始前取消。** is_cancelled 一开始就为 True。断言模型实际调用次数为 0，工具 handler 计数为 0。

**实验 B：同轮两个工具，第一项后取消。** 假模型一次提出两项调用。在第一项 tool_finished 事件回调中设置取消标志。第二项 handler 不得执行，也不得开始下一轮模型调用。

实验 B 用明确事件设置标志，不用随机 sleep 猜时序。保留第一项结果；assistant 历史可能仍有未完成的第二项请求，因为本次运行已经取消，不再把这段未完成历史发给模型。今天不实现恢复功能。

### 理解能力边界

边界检查不会立刻中断已经在等待的网络请求，更不能撤回已完成的工具副作用。它保证观察到取消之后不再启动新的模型/工具操作。

`Task.cancel()` 是另一种取消机制。若代码捕获 `asyncio.CancelledError` 来记录轨迹，清理后应重新抛出；不要将其误记为普通 failed。调用者应 await 被取消任务，观察清理完成。参考 [Python 3.11 任务取消说明](https://docs.python.org/3.11/library/asyncio-task.html#task-cancellation)。

外部 Task 取消后的落盘和强制终止复杂同步工具，属于扩展；不要声称今天已实现“任意操作立即取消”。

## 9. 阶段四：补全执行轨迹

沿用 `RunEvent`，统一事件种类。建议字段如下：

| kind | 记录内容 |
|---|---|
| run_started | run_id、初始状态、max_steps、model_mode |
| model_started | step、本轮输入 messages 深拷贝、工具定义快照 |
| model_finished | content、tool_calls、request_id、返回用量 |
| tool_started | step、tool_call_id、工具名、参数 |
| tool_finished | 与开始相同的关联字段、ToolResult、耗时 |
| run_finished | 最终状态、停止原因、次数、总耗时、最终回复 |

每个事件在 `data` 中带递增的 seq；step 表示所属模型轮次。先追加到本次结果的 events，再交给可选观察回调。

### 9.1 为什么快照需要深拷贝

错误示例：

```python
snapshots.append(messages)
```

后续追加消息时，旧快照可能一起变化。使用：

```python
from copy import deepcopy

snapshot = deepcopy(messages)
```

第一轮的快照应一直只有最初的消息，不因后面的工具调用而增长。可对照 [Python 深浅拷贝说明](https://docs.python.org/3.11/library/copy.html)。

### 9.2 用量不能重复累计

- 成功返回的 ModelReply 用量只通过 `usage.add(reply.usage)` 合并一次。
- `steps` 可表示模型调用尝试轮数；当前 `usage.model_calls` 来自成功返回的回复，不保证包括失败的 HTTP 请求或客户端内部重试。
- `usage.tool_calls` 沿用“提交给 Registry 的工具请求数”：未知工具、参数拒绝也算一次请求，不等于 handler 成功执行数。
- 必要时根据 tool_finished 的 ok 单独统计成功/失败数，不修改旧字段含义却不说明。
- 假模型 Token 只能作为测试夹具，标记 `model_mode=mock`，费用为 0。服务失败时无法从当前接口取得的用量，应写“未知”，不要伪造为真实费用 0。

### 9.3 保存一份可读轨迹

在 `examples/day05_agent_v0.py` 中，等 run_detailed 返回后调用独立导出函数。保存 events 为 JSONL，每行一个 JSON，并保存完整结果 JSON：

```python
from pathlib import Path
from research_agent.trace import save_trace

# result 来自不指定 run_id 的 await agent.run_detailed(...)。
events_path, result_path = save_trace(result, Path("data/day05"))
```

本例是正常返回后的保存，不是崩溃恢复或实时检查点。写文件失败应明确报错，不能打印“已保存”后忽略错误。

将 `data/day05/` 加入 `.gitignore`。导出器只接受 UUID hex run_id，拒绝已有文件覆盖。今天用公开合成问题保存完整输入输出；不要把 Settings、HTTP 请求头、API Key 写入事件。当前导出器不会自动脱敏，真实敏感输入需要另行设计摘要及脱敏策略。

注意当前 Pydantic 校验错误文本可能包含输入值。记录真实输入时不能仅凭“没有保存 headers”就认为已经脱敏。

**检查点：**不重新调用模型，仅阅读一份轨迹就能复述发生过的步骤；每次正常返回的运行恰好有一个 run_finished。

## 10. 阶段五：写一个可控的脚本假模型

不要依靠真实模型稳定复现未知工具、缺参、持续调用等异常。也不要让 DemoModel 的正则规则代替所有案例。

在 `tests/conftest.py` 中新增 fixture，提供下面这种按预设顺序返回的模型。已有文件只追加：

```python
from copy import deepcopy

import pytest

from research_agent.models import ModelReply


class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def complete(self, messages, *, tools=None, response_format=None):
        self.calls.append(deepcopy(messages))
        index = len(self.calls) - 1
        if index >= len(self.replies):
            raise AssertionError("发生了预期之外的额外模型调用")
        item = self.replies[index]
        if isinstance(item, Exception):
            raise item
        if not isinstance(item, ModelReply):
            raise AssertionError("测试脚本必须提供 ModelReply 或预期异常")
        return item.model_copy(deep=True)


@pytest.fixture
def scripted_model():
    return ScriptedModel
```

使用方式：测试函数接收 `scripted_model` 参数，传入一组回复，例如“调用计算器”再“最终文本”。ModelReply 的 Usage 在测试中显式设 `model_calls=1`；如果检查 Token，就显式提供合成数字。

这个模型收到第几次请求，就返回第几项。它没有根据问题智能选工具。除检查最终答案外，测试必须检查实际 tool 消息的内容，防止“没有执行工具，但假模型还是返回正确答案”的假通过。

## 11. 阶段六：完成 15 个固定 Agent 案例

新建 `curriculum/day-05-cases.md`，复制下面的案例表，补上实际测试函数、结果和证据。每个案例在 `tests/test_mini_agent.py` 中都有可运行断言。

表中 M 表示调用模型接口 complete 的次数，T 表示提交给 Registry 的工具请求次数；都以假模型与固定输入验证。这里不是客户端内部的 HTTP 重试次数。

| ID | 固定问题/场景 | 假模型安排 | 关键验收 |
|---|---|---|---|
| D05-01 | “用一句话解释 API” | 直接返回非空答案 | completed，M=1、T=0，最后一条为 assistant |
| D05-02 | “计算 12 * 8” | calculator → 最终回复 | completed，M=2、T=1，工具结果为 96 |
| D05-03 | “获取当前 UTC 时间” | current_time → 最终回复 | 时间能解析且有 UTC 偏移；不比较固定时间字符串 |
| D05-04 | “统计 hello agent” | text_statistics → 最终回复 | characters=11、non_whitespace=10、words=2 |
| D05-05 | “忽略大小写统计 Agent agent AGENT 中 agent 次数” | count_occurrences，case_sensitive=False → 回复 | 结果沿用当前契约 `{"text": 3}` |
| D05-06 | “使用一个不存在的工具” | unknown_tool → 说明失败 | tool 消息 ok=False；无真实 handler 执行；有最终解释则 completed |
| D05-07 | “计算器漏传表达式” | calculator，arguments={} → 说明失败 | 缺参被拒绝，handler 未执行，错误回传 |
| D05-08 | “计算器传入错误参数” | expression=123；再参数化测试多余字段 | 类型/额外字段拒绝；两种输入均不执行 handler |
| D05-09 | “计算 1 / 0” | calculator → 说明失败 | 实际执行失败，ok=False，进程不中断 |
| D05-10 | “分别计算 2+2 和 3*3” | 一轮两个 ToolCall，ID 不同 → 汇总回复 | M=2、T=2，两个结果为 4、9，ID 无错配 |
| D05-11 | 模型返回空白答案且没有工具 | 空白 content、空 tool_calls | failed，empty_response，M=1、T=0 |
| D05-12 | 模型服务返回预期错误 | complete 抛 LLMError | failed，保留错误类别；无工具、无后续模型调用 |
| D05-13 | 模型一直请求计算器 | 三轮工具调用，max_steps=3 | stopped，max_steps，M=3、T=3，无第四轮 |
| D05-14 | 用户在开始前取消 | 回调立即为 True | cancelled，M=0、T=0 |
| D05-15 | 第一项工具完成后取消 | 同轮两个工具，第一项完成事件设置标志 | cancelled，M=1、T=1，第二 handler 未执行 |

D05-08 可以生成两个 pytest 实例，因此实际收集数量可能大于 15。验收是这 15 种行为都有证据，不是强行凑总数。

### 每个成功案例同时检查

- 最终状态与停止原因。
- 实际 model.calls 次数，不只检查 Usage 数字。
- messages 中工具请求/结果的关联。
- tool 消息反序列化后的真实数值。
- 最终 assistant 回复已保存。
- 终止事件只有一个，之后没有新的 model_started/tool_started。

### 错误案例需要额外检查

- 校验失败时 handler 计数为 0。
- 执行错误时 handler 确实开始过，但错误被包装回传。
- failed/stopped/cancelled 不被标成 completed。
- 有成功回复解释工具失败的情况，与 Agent 控制流程本身失败区别记录。

### 补两项跨案例检查

1. 连续运行两个问题，第二次 messages 不包含第一次的问题、事件与累计用量。可以复用同一个 Agent 对象，但假模型脚本要覆盖两次运行需要的回复。
2. 第一轮事件中的 messages 快照不会在第二轮后改变；这验证深拷贝是否有效。

参数化可参考 [pytest 参数化文档](https://docs.pytest.org/en/stable/how-to/parametrize.html)。不同停止行为可以写独立测试，不必强行塞入一个巨大的参数表函数。

## 12. 阶段七：在 PyCharm 中做一次完整验收演示

### 12.1 新建演示文件

创建 `examples/day05_agent_v0.py`。先演示一条离线成功链路，再演示一次停止或取消。

可以复用 Day 04 的 CountDemoModel 思路，在本文件中定义独立的演示模型。不要让运行示例依赖 tests/conftest.py；示例和测试分别持有自己的简单入口。

演示文件应：

1. 构造模型与 builtin_registry。
2. 调用 `run_detailed()`。
3. 打印事件摘要。
4. 打印 run_id、status、stop_reason、answer、steps、调用次数与总耗时。
5. 调用 save_trace 保存本次合成案例的完整事件。

### 12.2 PyCharm 运行配置

| 配置项 | 内容 |
|---|---|
| 名称 | `Day05 Mini Agent v0` |
| 类型 | Python，脚本路径 |
| 脚本 | `E:\agent_project\agent-learning-lab\examples\day05_agent_v0.py` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | `E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe` |

旧 CLI 用模块配置回归：

```text
模块名称：research_agent.cli
参数：demo "计算 12 * 8"
工作目录：E:\agent_project\agent-learning-lab
```

不要直接把包内 cli.py 当脚本启动，否则相对导入可能失败。

### 12.3 断点顺序

1. 初始化本次结果对象。
2. 模型调用前快照处。
3. 判断是否有 tool_calls 的分支。
4. Registry 调用前与返回后。
5. 写入 tool 消息的位置。
6. 统一收尾位置。

观察模型第一次、第二次输入的差别，以及从 running 进入终态的位置。耗时数据用普通运行模式采集，不用被断点暂停的结果比较性能。

### 12.4 用 3～5 分钟讲解

按这个顺序讲：

```text
用户给问题
→ 程序给模型消息和工具定义
→ 模型决定是否请求工具
→ 程序查找、校验、执行
→ 结果通过 tool 消息进入下一轮上下文
→ 最终回复或明确停止
```

接着展示一次错误或取消，说明程序在哪里停止，以及哪些操作没有再发生。

## 13. 阶段八：运行测试、保存证据

先在 PyCharm 右键单个新测试运行，修复后运行整个 Agent 测试文件：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mini_agent.py -q
```

再运行直接相关的回归：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tools.py tests/test_mini_agent.py tests/test_llm.py -q
```

由于今天可能修改共用 models.py，相关检查通过后运行一次完整测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

记录真实输出，区分功能断言失败与运行环境问题。若遇到之前出现过的临时目录权限问题，先确认失败路径，不要据此修改 Agent 业务逻辑。

需要一个可写测试临时目录时，可使用明确的新目录，例如：

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest_cache/day05-temp -p no:cacheprovider
```

这个目录只用于 pytest 临时数据；pytest 可能清理 basetemp 内容，不要指定项目根目录或存有学习成果的目录。已有路径不可写时，选择另一个专用空目录并加入 .gitignore。

最终报告建议：

```markdown
| 案例 ID | 测试函数 | 预期状态 | 实际状态 | 结果 | 证据 |
|---|---|---|---|---|---|
| D05-01 | ... | completed | 待运行 | 待运行 | |
```

报告里的“通过”必须来自运行后的断言，不能只凭阅读代码填写。全部行为测试离线运行，无需 API Key。

## 14. 第一周复盘与提交

### 14.1 学习日志

新建 `curriculum/day-05-log.md`，至少写：

- Mini Agent v0 的数据流图与状态转移说明。
- Day 04 遗留测试修复了什么，为什么原来的测试可能假通过。
- 15 个案例的结果表或指向案例文档的链接。
- 一次成功与一次异常运行的脱敏轨迹节选。
- model_calls、tool_calls、steps、总耗时分别是什么意思。
- 当前取消方式、模型失败用量未知等边界。
- 五天分别学到了什么，自己仍然解释不清什么。

### 14.2 提交

先检查项目 Git 状态：

```powershell
git status
git diff --check
```

如尚未建仓，确认项目目录后初始化，并先补项目基础提交。已有仓库直接检查本次变更。

按实际文件修改暂存：

```powershell
git add src/research_agent/models.py src/research_agent/mini_agent.py tests/test_tools.py tests/test_mini_agent.py tests/conftest.py examples/day05_agent_v0.py curriculum/day-05-pycharm.md curriculum/day-05-cases.md curriculum/day-05-log.md .gitignore
git diff --cached --stat
git status
git commit -m "learn: complete mini agent v0 states traces and cases"
```

额外改过 cli.py 等文件时，检查后补入；没有创建的路径从命令中去掉。确保没有密钥和本地敏感轨迹进入暂存区。

标签不是今天核心验收要求。若全部核心项已验收，可自愿创建本地里程碑标签 `day05-mini-agent-v0`，无需推送远程。

## 15. 有余力再做的扩展

1. 选 2～3 个公开问题使用 DeepSeek 重跑，比较真实选择与脚本预设的差异，记录实际请求和 Token。不要重新把 15 条故障案例全部发送给真实 API。
2. 为 CLI 增加 `--trace` 开关，选择输出事件摘要或保存本地轨迹。
3. 把收尾后的 JSONL 保存改成每步追加，讨论崩溃后能保留多少证据；这仍不等于恢复任务。
4. 为可协作取消的异步工具增加单次超时，重用 Day 03 的实验；不能把它宣称为同步阻塞函数的硬中断。
5. 增加工具调用总数上限、输出长度上限，并用独立测试证明；与 max_steps 区分。

## 16. 今日最终验收标准

- [x] 旧 demo 和 Day 04 示例仍可运行。
- [x] 新接口明确返回 completed、failed、cancelled、stopped。
- [x] 普通问题可以不调用工具直接回答。
- [x] 工具失败被记录并回传，不直接导致进程崩溃。
- [x] 模型预期服务错误有明确失败状态。
- [x] 每次模型输入、输出、工具请求与结果都有可检查证据。
- [x] 正常返回的运行恰好生成一条终止事件。
- [x] 观察到取消后不启动新的模型或工具操作。
- [x] 达到最大轮数后终止，不伪装为完成。
- [x] 15 个固定案例都有可执行断言与真实结果。
- [x] 多次运行之间没有共享消息或累计用量污染。
- [x] 已提供可重建流程的轨迹、讲解稿及口头题参考答案。
- [ ] 学习者不看稿、用自己的话讲解（需本人验收）。
- [x] 完成日志、相关回归与 Day 05 本地 Git 提交。

今天完成的是可解释的教学版 Mini Agent v0。它尚不具备完整搜索、RAG、任务恢复或生产级权限管理，后续课程会逐步补上。

## 17. 不看笔记的口头验收

1. 一个模型 API 调用与一个 Agent 循环有什么区别？
2. 用户输入、模型消息、工具参数、工具结果分别存在哪里？
3. 为什么工具调用前后通常需要两轮模型请求？
4. 工具失败后，Agent 是否必须立刻变成 failed？
5. completed 与“用户目标已成功实现”是否完全相同？
6. 为什么不能通过回复字符串里有没有“失败”来判断状态？
7. 最大步数、调用次数和总耗时分别限制或衡量什么？
8. 为什么只在每轮开头检查取消可能不够？
9. 为什么 messages 快照不能只保存原列表引用？
10. 假模型的正确回答为什么不能证明工具真的执行了？
11. 怎样证明测试没有访问真实 API？
12. 如果明天加入网页搜索，它应该进入当前哪一层？

最后画一次从 query 到 answer 的完整流程。能脱离框架名词讲清楚，就达到了第一周的主要学习目标。

## 18. 参考资料与下一天衔接

- [Python 3.11：协程取消](https://docs.python.org/3.11/library/asyncio-task.html#task-cancellation)
- [Python 3.11：深浅拷贝](https://docs.python.org/3.11/library/copy.html)
- [pytest：参数化测试](https://docs.pytest.org/en/stable/how-to/parametrize.html)

Day 06 会开始网页搜索与正文提取。届时将工具从计算和文本处理扩展到外部信息获取，继续沿用今天建立的输入、结果、错误与轨迹契约。
