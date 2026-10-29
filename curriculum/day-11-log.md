# Day 11 学习日志：LangGraph 的 State、Node、Reducer、条件边与可观察研究图

整理日期：2026-10-29。项目：`E:\agent_project\agent-learning-lab`。

本日志记录本轮 Day 11 实际完成的代码、实验、测试和理解，方便以后快速恢复上下文。代码由 AI 协助设计和补齐；“测试通过”只证明当前自动化场景满足约定，不等于已经能够脱离代码独立实现，也不等于图已经具备生产级恢复、并行和真实模型稳定性。

## 先用三分钟回忆这一天

Day 11 的主题不是提高回答质量，而是把已有 Python 工作流拆成可观察的图，并明确每个字段怎样在节点之间传递。

这一轮完成了两张不同用途的图：

```text
工具循环图
START → model → tools → model → ... → END

研究流程图
START → plan → retrieve → curate
                         ├─ write → validate → END
                         ├─ no_evidence → END
                         └─ failed → END
```

最需要记住的结论：

1. State 是一次运行的数据快照；Node 是读取快照并返回局部更新的函数。
2. 节点通常返回更新字典，不原地修改输入 State，也不机械地 `return state`。
3. 没有 Reducer 的字段默认覆盖；`operator.add` 字段追加节点返回的增量。
4. 追加字段若返回“旧列表 + 新条目”，Reducer 会再次拼接旧列表，造成重复。
5. 路由函数只读取 State 并选择下一跳，不调用模型、工具或修改状态。
6. `model_calls` 是业务停止条件，`recursion_limit` 是框架最后保护，两者不能混用。
7. `ainvoke`、`astream(updates)` 和 `astream(values)` 如果分别调用，就是三次真实执行。
8. 图到达 END 只代表流程结束；研究回答仍可能是 `awaiting_review`，不是已正式批准。

## 一、核心概念怎样对应到当前代码

| 概念 | 当前项目中的含义 | 例子 |
| --- | --- | --- |
| State | 一次图运行中需要跨节点保存的数据 | `ToolGraphState`、`ResearchGraphState` |
| Node | 读取 State、完成单一职责、返回局部更新 | `model`、`tools`、`plan`、`retrieve` |
| Edge | 节点之间固定的执行方向 | `plan → retrieve` |
| Conditional Edge | 根据当前 State 选择下一跳 | `curate → write/no_evidence/END` |
| Reducer | 同一字段旧值与节点更新的合并规则 | `trace: Annotated[list[str], operator.add]` |
| Compile | 将节点和边编译成可调用图 | `builder.compile()` |

一次状态变化可以用下面的公式理解：

```text
原状态 + 节点返回的更新 + 字段合并规则 = 新状态
```

例如 `status` 没有 Reducer，所以覆盖：

```text
旧 status="retrieving"
+ retrieve 返回 status="curating"
= 新 status="curating"
```

`trace` 使用 `operator.add`，所以追加：

```text
旧 trace=["plan:completed"]
+ retrieve 返回 trace=["retrieve:found:1"]
= 新 trace=["plan:completed", "retrieve:found:1"]
```

## 二、Reducer 与 Python 可变对象

最小实验需要区分三种情况。

### 1. 普通列表字段默认覆盖

```python
class DemoState(TypedDict):
    trace: list[str]
```

若 prepare 返回 `['prepare']`，finish 返回 `['finish']`，最终只保留：

```python
["finish"]
```

### 2. 使用追加 Reducer 时返回增量

```python
trace: Annotated[list[str], operator.add]
```

正确节点更新：

```python
return {"trace": ["finish"]}
```

旧值 `['prepare']` 与增量 `['finish']` 合并，得到：

```python
["prepare", "finish"]
```

### 3. 追加字段返回全量会重复

错误写法：

```python
return {"trace": state["trace"] + ["finish"]}
```

节点已经返回 `['prepare', 'finish']`，Reducer 又与旧值 `['prepare']` 拼接，结果为：

```python
["prepare", "prepare", "finish"]
```

`operator.add` 不去重，也不知道哪个条目已经存在。它只执行拼接。

### 4. 不原地修改 State 内的可变对象

不推荐：

```python
state["trace"].append("finish")
return {"trace": state["trace"]}
```

推荐把输入 State 当作只读快照，构造新更新：

```python
return {"trace": ["finish"]}
```

当前项目的 `Usage.add()` 也会原地修改接收者。因此 `graph_state.py` 中新增了：

```python
def accumulate_usage(current: Usage, delta: Usage) -> Usage:
    updated = current.model_copy(deep=True)
    updated.add(delta)
    return updated
```

节点使用新对象覆盖 `usage`，不会修改输入 State 中原有的 Usage。

## 三、工具循环图：model 与 tools

新增 `src/research_agent/tool_graph.py`，实现与官方 Quickstart 等价的本地工具循环，但使用项目已有的 `ChatModel` 和 `ToolRegistry` 接口。

图结构：

```text
START
  ↓
model
  ├─ completed / stopped / failed → END
  └─ 有工具请求且未达上限 → tools
                                  ↓
                                model
```

### ToolGraphState 保存什么

| 字段 | 规则 | 含义 |
| --- | --- | --- |
| messages | 追加 | 用户、模型、工具消息历史 |
| trace | 追加 | 本次节点轨迹 |
| model_calls | 覆盖 | 已发生的模型调用数 |
| max_model_calls | 稳定 | 业务调用上限 |
| pending_tool_calls | 覆盖 | 等待执行的工具请求 |
| status | 覆盖 | running/completed/stopped/failed |
| stop_reason | 覆盖 | 明确停止原因 |

### model 节点负责什么

1. 调用 `model.complete(messages, tools=registry.definitions())`。
2. 保留工具调用的 ID、名称和参数。
3. 增加 `model_calls`。
4. 判断最终回答、工具请求、空回复、协议错误或达到业务上限。
5. 在节点内设置明确的 `status` 和 `stop_reason`。

第三次模型调用即使达到上限，只要产生正常最终回答，仍应 `completed`。只有第三次仍请求新工具时才 `stopped`，并且不执行这批新工具。

### tools 节点负责什么

1. 只通过项目 `ToolRegistry.invoke(name, arguments)` 执行注册工具。
2. 不根据模型字符串访问 `globals()` 或执行任意函数。
3. 为每个请求生成具有相同 `tool_call_id` 的工具消息。
4. 未知工具和参数错误转换成明确观察，让下一轮模型决定怎样响应。

### 两个上限的区别

| 上限 | 控制对象 | 正常用途 |
| --- | --- | --- |
| `max_model_calls` | 模型业务调用次数 | 得到可解释的 stopped 状态 |
| `recursion_limit` | LangGraph 图步骤数 | 防止异常无限循环 |

`model → tools → model` 已经经过多个图步骤，因此不能把两者设成同一个概念。

### 工具图实际验证

`examples/day11_tool_graph.py` 支持：

```text
direct_answer
one_tool
bad_arguments
unknown_tool
empty_reply
endless_tools
```

一次工具后回答的实际结果：

```text
status=completed
model_calls=2
trace=model:requested_tools → tools:success:calculator → model:completed
```

永远请求工具且 `max_model_calls=3`：

```text
model 1 → tools
model 2 → tools
model 3 → stopped
```

第三次工具请求没有执行，工具实际只调用两次。

## 四、研究图状态：哪些是快照，哪些是依赖

新增 `src/research_agent/graph_state.py`。它只定义研究图的数据契约，不执行模型、检索或图连线。

`ResearchGraphState` 的主要数据链：

```text
query
  ↓ plan
plan
  ↓ retrieve
candidates
  ↓ curate
evidence_scope
  ↓ write
answer_result
  ↓ validate
report_preview
```

字段约定：

| 字段 | 更新方 | 规则 |
| --- | --- | --- |
| task_id/query | 初始化 | 稳定，不由节点更新 |
| plan | plan | 覆盖完整计划 |
| candidates | retrieve | 覆盖本次完整候选 |
| evidence_scope | curate | 覆盖证据范围 |
| answer_result | write | 覆盖完整回答结果 |
| report_preview | validate | 覆盖待审预览 |
| status/stop_reason | 各节点 | 覆盖 |
| trace/errors | 各节点 | 追加本节点增量 |
| usage | 发生调用的节点 | 复制旧值、加本次增量、覆盖累计值 |

`ResearchGraphUpdate` 是节点返回值的类型约定。它故意不包含 `task_id` 和 `query`，提醒节点不要更新任务身份和原问题。TypedDict 只提供静态类型帮助，不会在运行时自动阻止额外字段。

`create_research_graph_state()` 每次创建新的列表、Usage 和任务 ID，避免两次运行共享可变对象。显式空 query 和空 task_id 会被拒绝。

### 为什么不继续使用旧 sources/evidence/report

旧字段容易混淆不同阶段：

```text
原始/检索候选来源 → candidates
预算后真正可见来源 → evidence_scope.visible_sources
模型与程序校验结果 → answer_result
允许展示的待审草稿 → report_preview
```

`candidates` 不等于模型实际看见的来源；`answer_result` 也不等于已经审核批准的正式报告。

### State 与服务依赖的判断方法

```text
描述“本次任务发生了什么” → 放进 State
描述“系统凭什么完成任务” → 构建图时注入
```

放进 State 的内容包括问题、计划、候选、证据范围、回答、状态、错误、轨迹和本次 Usage。

不放进 State 的内容包括模型客户端、检索器、Settings、API Key、HTTP 客户端、数据库连接、锁和事件回调。

## 五、五个研究节点分别做什么

`plan/retrieve/curate/write/validate` 是节点名，不是五份 State。完整 State 只有一份，节点依次读取并返回局部更新。

| 节点 | 读取 | 返回的主要更新 | 作用 |
| --- | --- | --- | --- |
| plan | query | plan、status、trace | Day 11 暂时使用固定 `[query]` |
| retrieve | query、plan | candidates、status、trace | 获取检索候选 |
| curate | candidates | evidence_scope、status、stop_reason | 筛选允许且装得进预算的证据 |
| write | query、evidence_scope | answer_result、usage、status | 生成并完成 Day 10 程序校验 |
| validate | answer_result、evidence_scope | report_preview、status | 生成明确标记的待审预览 |

状态名称描述节点执行后的阶段，例如 plan 完成后返回 `status="retrieving"`。`planning/retrieving/...` 是字段值，不会自动调度同名节点；实际调度由边决定。

## 六、用局部更新构建五节点研究图

新增 `src/research_agent/graph_workflow.py`，旧 `workflow.build_langgraph()` 保留作为教学对比，没有替换 API 入口。

旧图：

```text
START → research（内部执行整个 ResearchWorkflow.run）→ END
```

新图：

```text
START → plan → retrieve
                  ├─ failed → END
                  ↓
                curate
                  ├─ ready → write
                  ├─ no evidence → no_evidence → END
                  └─ failed → END
                write
                  ├─ success → validate → END
                  └─ failed → END
```

### 依赖注入和适配器

`ResearchGraphServices` 注入：

```text
retriever
answer_service
canonical_sources
filters
max_context_chars
base_dir
```

实现了两个薄适配器：

- `Day09RetrieverAdapter`：调用 `TwoBranchRetriever.search()`，按计划串行检索，并按 source_id 保留首次结果。
- `Day10AnswerService`：调用已有 `generate_answer()`，保留 Day 10 的 JSON、引用、校验、修复和 Usage 规则。

Day 11 暂时串行处理计划子问题，没有引入并行合并语义。并行写冲突和聚合策略留到 Day 13。

### curate 条件边

`prepare_evidence_scope()` 可能得到：

```text
ready
no_candidates
no_allowed_sources
budget_exhausted
```

只有 ready 才进入 write。其他三种进入 no_evidence，不调用模型。路由函数只读取 status，不产生副作用。

### write 的 Usage 边界

`AnswerResult.usage` 已包含生成和最多一次修复的总用量。write 节点只累计这份完整结果一次：

```python
usage = accumulate_usage(state["usage"], result.usage)
```

不能再遍历 `attempts` 把每次 reply.usage 加一遍，否则重复计费。

### validate 的审核边界

`generate_answer()` 返回 `program_validated` 只表示结构和来源程序校验通过。当前学习图调用 `render_answer_preview()`，最终状态为：

```text
awaiting_review
```

不是 `approved`，也不把待审内容当作正式报告。当前学习图只为 `support_review="pending"` 的结果生成预览。

## 七、观察 updates、values 和最终状态

新增 `examples/day11_research_graph.py`，完全离线，使用固定 Source、FakeRetriever 和 FakeAnswerModel。

支持案例：

```text
evidence_available
no_candidates
retrieval_failure
```

支持模式：

```text
ainvoke
updates
values
mermaid
all
```

### ainvoke

```python
result = await graph.ainvoke(initial)
```

返回最终完整 State。成功案例实际得到：

```text
status=awaiting_review
candidate_count=1
evidence_status=ready
answer_status=program_validated
has_report_preview=true
usage.model_calls=1
usage.total_tokens=15
```

### astream updates

```python
async for event in graph.astream(initial, stream_mode="updates"):
    ...
```

每个事件形如：

```python
{
    "retrieve": {
        "candidates": [...],
        "status": "curating",
        "trace": ["retrieve:found:1"],
    }
}
```

外层键是节点名，内层是节点局部更新。它不是完整 State，未出现 query 不代表 query 丢失。

### astream values

```python
async for state in graph.astream(initial, stream_mode="values"):
    ...
```

每次返回合并后的完整快照。成功案例观察到：

```text
initialized
→ retrieving
→ curating
→ writing
→ validating
→ awaiting_review
```

对应轨迹逐步累积：

```text
plan:completed
retrieve:found:1
curate:ready:1
write:program_validated
validate:awaiting_review
```

### 三种调用是三次执行

`--mode all` 实际执行 ainvoke、updates、values 三遍。演示输出确认：

```text
retriever_calls=3
model_calls=3
```

这不是一次运行的三个视角回放。真实模型路径不要为了观察而无意重复付费。每次运行都通过 `create_research_graph_state()` 创建独立初始状态。

### 无证据实际轨迹

```text
plan
→ retrieve:found:0
→ curate:no_candidates
→ no_evidence:no_candidates
→ END
```

实际计数：

```text
retriever_calls=1
model_calls=0
```

### 检索失败实际轨迹

```text
plan:completed
→ retrieve:failed
→ END
```

最终状态：

```text
status=failed
stop_reason=unexpected_error
model_calls=0
```

演示输出只记录状态摘要、字段名、数量、Usage 和耗时，不打印完整原始文档、Prompt 或密钥。

## 八、Mermaid 图与实际路径

研究图通过以下代码输出 Mermaid：

```python
mermaid = graph.get_graph().draw_mermaid()
print(mermaid)
```

当前编译图包含节点：

```text
__start__
plan
retrieve
curate
write
validate
no_evidence
__end__
```

Mermaid 图表示所有可能路径，一次 trace 只表示本次实际走过的路径。能从图预测成功、无证据和失败轨迹，再用 updates/values 核对，是阶段七的检查点。

运行 Mermaid 输出：

```powershell
.\.venv\Scripts\python.exe examples\day11_research_graph.py --mode mermaid
```

当前脚本会打印源码；尚未另外创建 `curriculum/day-11-graphs.md` 文件。

## 九、实际测试与验证结果

阶段四到六的针对性测试：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_graph_state.py `
  tests\test_tool_graph.py `
  tests\test_graph_workflow.py -q
```

实际结果：

```text
14 passed in 0.33s
```

加入旧工作流和 Day 10 RAG 回归：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_workflow.py `
  tests\test_rag.py `
  tests\test_graph_state.py `
  tests\test_tool_graph.py `
  tests\test_graph_workflow.py -q
```

实际结果：

```text
93 passed in 0.51s
```

这些测试验证了：

- 初始 State 不共享列表和 Usage。
- Usage 累计不修改输入对象。
- 工具循环一次工具后正常回答。
- 永久工具请求在业务上限停止。
- 最后一轮正常回答不会被误判为超限。
- 成功研究路径经过五个节点并得到待审预览。
- 无候选路径不调用 write/model。
- 检索失败直接进入明确失败终态。
- AnswerResult Usage 只累计一次。
- 旧工作流和 Day 10 RAG 规则没有因新图回归。

## 十、本轮实际遇到的问题

### 1. Windows asyncio 在沙箱内看起来像测试卡死

第一次运行新异步测试时，pytest 停在第一个异步用例。`faulthandler` 显示线程卡在 Python 创建 Windows asyncio 事件循环的底层 socketpair，而测试函数尚未开始。

最小命令 `asyncio.run(asyncio.sleep(0))` 在同一沙箱中也会卡住，说明不是 LangGraph 条件边形成死循环。改为在沙箱外运行同一套完全离线测试后立即通过。

学到的是：遇到“图不结束”时先确认卡在哪一层。测试函数尚未开始、事件循环无法创建，与节点路由死循环是不同问题。不要看到超时就直接修改图逻辑。

### 2. Windows 终端中文编码

演示第一次运行时，工具捕获的中文显示乱码。脚本增加：

```python
sys.stdout.reconfigure(encoding="utf-8")
```

之后无证据和失败演示能正常显示中文。这个修改只影响输出编码，不改变状态内容。

### 3. 通用 Tool 接口与项目真实接口不同

最初设计工具图时需要确认项目真实接口。项目不是直接从字典取得工具，而是：

```python
registry.definitions()
await registry.invoke(name, arguments)
```

模型接口也需要接收 `tools=...`。最终工具图按现有 `ChatModel`、`ToolRegistry` 和 `ToolResult` 适配，没有绕过项目参数校验。

## 十一、文件导航

以下路径相对项目根目录。

| 文件 | 用途 |
| --- | --- |
| `src/research_agent/graph_state.py` | 研究图 State、Update、初始化和 Usage 累计 |
| `src/research_agent/tool_graph.py` | model/tools 工具循环、条件路由与业务上限 |
| `src/research_agent/graph_workflow.py` | 五节点研究图、无证据分支、Day 09/10 适配器 |
| `examples/day11_tool_graph.py` | 工具循环的离线案例演示 |
| `examples/day11_research_graph.py` | ainvoke、updates、values、Mermaid 演示 |
| `tests/test_graph_state.py` | 初始化隔离、输入校验、Usage 复制累计 |
| `tests/test_tool_graph.py` | 工具循环与调用上限 |
| `tests/test_graph_workflow.py` | 成功、无证据、检索失败和 Usage 路径 |
| `src/research_agent/workflow.py` | 旧普通工作流和旧单节点 build_langgraph，对照保留 |
| `src/research_agent/rag.py` | Day 10 证据准备与回答生成服务 |
| `src/research_agent/rag_render.py` | 待审预览和正式报告渲染 |
| `src/research_agent/retrieval_pipeline.py` | Day 09 两路检索接口 |

## 十二、以后从哪些命令重新进入

工具循环：

```powershell
.\.venv\Scripts\python.exe examples\day11_tool_graph.py --case one_tool
.\.venv\Scripts\python.exe examples\day11_tool_graph.py --case endless_tools --max-model-calls 3
```

研究图成功路径：

```powershell
.\.venv\Scripts\python.exe examples\day11_research_graph.py `
  --case evidence_available --mode all
```

只看局部更新：

```powershell
.\.venv\Scripts\python.exe examples\day11_research_graph.py `
  --case evidence_available --mode updates
```

观察无证据条件边：

```powershell
.\.venv\Scripts\python.exe examples\day11_research_graph.py `
  --case no_candidates --mode updates
```

观察失败终态：

```powershell
.\.venv\Scripts\python.exe examples\day11_research_graph.py `
  --case retrieval_failure --mode ainvoke
```

输出 Mermaid：

```powershell
.\.venv\Scripts\python.exe examples\day11_research_graph.py --mode mermaid
```

## 十三、已经完成与尚未完成

### 已完成

- 定义独立的研究图 State 和字段更新规则。
- 验证覆盖、追加、增量返回和可变对象隔离原则。
- 实现 model/tools 有界工具循环。
- 实现 plan/retrieve/curate/write/validate 五节点研究图。
- 添加 no_evidence 条件分支和失败终态路由。
- 接入 Day 09 检索薄适配器和 Day 10 Mock 回答路径。
- 保留旧单节点 build_langgraph 作教学对照。
- 用 ainvoke、updates、values 观察执行。
- 输出并核对 Mermaid 图结构。
- 完成针对性测试和相关回归测试。

### 尚未完成或不在 Day 11 范围

- 没有把新研究图替换到 API 生产入口。
- 没有使用真实 DeepSeek 验证工具循环或研究图。
- 没有实现 SQLite checkpointer、interrupt/resume 或跨进程恢复。
- 没有实现并行检索分支和并行字段合并；留到 Day 13。
- 没有实现复杂规划质量；plan 仍固定为 `[query]`，留到 Day 12。
- 没有创建单独的 `examples/day11_state_lab.py`；Reducer 原理已解释并由状态测试覆盖，但课程建议的独立最小脚本仍可补充。
- 尚未单独创建 `curriculum/day-11-graphs.md`，Mermaid 目前由演示脚本输出。
- 当前新增文件和修改尚未完成 Git 提交收尾。
- Day 09 适配器已实现，但本轮整图测试使用确定性 FakeRetriever，没有用真实索引做端到端研究图实验。

## 十四、以后复习时先问自己

1. Node 为什么返回部分更新，而不是修改并返回整个 State？
2. 普通 list 字段和 `Annotated[list, operator.add]` 的结果有什么区别？
3. 为什么追加字段返回 `state["trace"] + [new]` 会重复旧条目？
4. 为什么 `Usage.add()` 之前要复制旧 Usage？
5. `ToolGraphState` 与 `ResearchGraphState` 分别回答什么问题？
6. `plan/retrieve/curate/write/validate` 为什么是节点，不是五个 State？
7. status 字符串为什么不会自动调度同名节点？
8. route 函数为什么不能调用模型或修改状态？
9. 第三次模型调用产生最终回答时，为什么仍然允许 completed？
10. `max_model_calls` 与 `recursion_limit` 分别限制什么？
11. `candidates` 与 `evidence_scope.visible_sources` 为什么不能混为一谈？
12. 为什么 no_candidates 路径不能调用 write？
13. `program_validated` 为什么最终仍是 `awaiting_review`？
14. 为什么不能把 `AnswerResult.usage` 和 attempts 的每次用量再同时累计？
15. updates 与 values 分别显示什么？
16. 为什么先 ainvoke 再分别 astream 两次会执行三遍图？
17. 哪些对象属于运行快照，哪些对象属于依赖注入？
18. 旧单节点图为什么看不到检索、整理、写作和验证的中间变化？
19. 图到达 END 为什么不等于报告事实已经得到证明？
20. 当前图为什么还不能承诺 SQLite 恢复或并行安全？

如果能够不看代码回答这些问题，并能修改一个节点而不破坏状态契约和其他路径，才算把 Day 11 从“代码能够运行”推进到了“能够独立解释和维护”。
