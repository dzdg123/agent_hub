# Day 09 阶段六：受字符预算约束的上下文

本阶段接收阶段四过滤、阶段三融合和阶段五 ID 去重后的有序 Source。
`build_context` 按该顺序尝试完整证据块，放不下时跳过并继续尝试后面的块。
它不会再次检索，不会重新排名或修改正文、offset，也不会按文件或正文删除其他出处。

## 接入现有检索器

```python
from research_agent.context import build_context

retrieval = retriever.search(
    "offset", candidate_k=6, top_k=3,
    filters={"file_types": {"pdf"}},  # 可省略，沿用阶段四接口
)
context = build_context(retrieval.final_sources, max_context_chars=2000)
print(context.text)
print(context.included_source_ids)
print(context.omitted_source_ids)
print(context.omission_reasons)
print(context.status, context.used_chars, context.budget)
assert len(context.text) <= context.budget
```

`retriever` 是已经用同一份规范 Source 初始化的 `TwoBranchRetriever`。
`search()` 的接口和返回值没有改变。调用 `.retrieve_candidates()` 尚未融合时，
不应将其 `final_sources` 传入构建器。

`candidate_k` 控制每路候选上限，`top_k` 控制融合后条数，`max_context_chars`
控制这批融合结果实际进入上下文的字符数。因此最终放入的证据数可能小于 top_k。
本阶段不自动从 top_k 之外补充候选。

## 新接口与入口

实现文件：`src/research_agent/context.py`。

| 接口 | 输入 | 返回 / 作用 |
| --- | --- | --- |
| `build_context(sources, *, max_context_chars=2000)` | 按融合排名排列、ID 唯一的 `list[Source]` | `ContextResult`，执行预算检查和整块装入 |
| `format_source_block(source)` | 一个 `Source` | 格式化完整证据块，保留来源和正文 |
| `render_context(blocks)` | 格式化后的 `list[str]` | 添加统一外壳和分隔符，空列表返回 `""` |
| `_label(value)` | 来源标签字符串 | 内部助手：JSON 引号和转义保证标签显示为单行；不处理正文 |

证据块包括 source_id、标题、文件、物理页、可选网址、位置 `[offset, end_offset)`、
坐标基准和完整正文。位置是左闭右开区间，直接读取原 metadata，不按显示文本的位置重新计算。
缺少来源字段时明确显示“未知”；无有效 offset/end_offset 时不猜测坐标。
来源标签使用 JSON 字符串表示，例如 `[source_id: "doc-offset"]`，引号不属于原 ID。
完整正文保留空格、换行和 Unicode 字符；块尾另加边界标记，该标记也计入预算。

每次尝试都调用同一个 `render_context` 生成拟议文本，检查 `len(text)`。
外层说明、块首尾标记、标题、文件信息、块间分隔符和全部换行均计数。
空输入或所有块都放不下时，返回空文本，不单独输出外壳。

### ContextResult 字段

| 字段 | 含义 |
| --- | --- |
| `text` | 最终上下文文本 |
| `included_source_ids` | 已放入文本的来源 ID，保留输入顺序 |
| `omitted_source_ids` | 未放入文本的来源 ID，保留输入顺序 |
| `used_chars` | 精确等于 `len(text)` |
| `budget` | 本次 max_context_chars |
| `omission_reasons` | 按遗漏 source_id 查询 `OmissionReason` |
| `status` | `ok` / `partial` / `budget_exhausted` / `empty_input` |

`ok` 表示全部放入，`partial` 表示只放入部分，
`budget_exhausted` 表示有输入但没有任何完整块放得下，
`empty_input` 表示没有输入证据。

### OmissionReason 字段

| 字段 | 含义 |
| --- | --- |
| `reason` | `block_exceeds_total_budget`：该块加外壳单独就超预算；`insufficient_remaining_budget`：单独放得下，但尝试时剩余空间不足 |
| `block_chars` | 该证据块自身长度，含块内标题和首尾标记，不含全局外壳、块间分隔符 |
| `required_chars` | 在尝试当时添加此块所需的增量字符数；首块包含外壳，后续块包含分隔符 |
| `remaining_chars` | 尝试该块之前的剩余预算 |

这些诊断记录尝试当时的状态，后续更短块仍可能进入上下文。
预算必须为正整数，0、负数、小数、字符串、bool 都抛 `ValueError`，空输入也先校验预算。
输入有空白 ID 或重复 ID 同样抛 `ValueError`，应由上游先完成融合去重。

## 运行实验

在项目根目录运行，无需加载 Embedding 模型：

```powershell
.\.venv\Scripts\python.exe examples/day09_context.py
```

`make_demo()` 创建三段不同长度、不同证据的规范 Source，来源为同一 PDF 不同物理页；
两个分支都按 offset、max_steps、model_name 排列。`main()` 只融合一次，
用不同预算反复构建上下文并输出正文和 ID，检查规范来源、候选和融合结果均未改变。

默认案例的结果：

| 预算 | 使用字符数 | 已放入 ID | 状态 |
| --- | --- | --- | --- |
| 2000 | 1181 | doc-offset、doc-steps、doc-model | ok |
| 444 | 444 | doc-steps、doc-model | partial |
| 194 | 194 | doc-model | partial |
| 1 | 0 | 无 | budget_exhausted |

预算可以重复指定：

```powershell
.\.venv\Scripts\python.exe examples/day09_context.py --budget 2000 --budget 500 --budget 250
```

也可以复用阶段二/四保存的候选，重新做一次 RRF 后比较预算，无需调用模型：

```powershell
.\.venv\Scripts\python.exe examples/day09_context.py `
  --candidates-json data/day09/candidates/<运行目录>/candidates.json `
  --top-k 3 --budget 2000 --budget 500
```

真实候选会使用已有加载器验证固定语料指纹。实验输出保存在
`data/day09/context/<独立运行目录>/context.json`，包括规范 Source 快照、
融合结果、每个预算的完整输出和 `inputs_unchanged`。可通过 included_source_ids
查回规范 Source 的文件、物理页和原坐标。

## 测试与限制

`tests/test_context.py` 检查精确预算及差一个字符、外壳计数、跳过长块继续、
完整正文和坐标不变、同文件不同页、空输入、全部放不下、非法预算、重复 ID、
未知来源字段、遗漏 ID 分区和实验落盘。
`tests/test_source_filters.py` 的真实 Chroma 集成测试延伸到上下文：
仅选 PDF 后 TXT 不进入上下文，不存在的文件得到空上下文。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_context.py tests/test_source_filters.py -q
```

这是可复现的贪心教学策略，可能跳过排名最高的长证据，不是最优装包算法。
`included_source_ids` 表示“提供给模型的证据”，不自动表示模型实际引用或答案得到支持；
遗漏来源不得列为已经提供的证据。

预算单位是 Python 字符数（`len(str)`），不是字节数、视觉字符数或模型 token 数。
它不包含外部系统提示、用户问题、其他消息和输出预留。Day 10 接入 DeepSeek 时需
另外计算完整请求预算；不能把 BGE tokenizer 当成 DeepSeek 精确计数器。

检索正文始终是不可信资料。外层文本标记资料边界并说明其中的指令不构成授权，
但分隔符本身不能保证防住提示注入。接入模型时保持资料在明确的数据区域，
不要将正文升级为新的 system 指令；本阶段未接入模型调用。
