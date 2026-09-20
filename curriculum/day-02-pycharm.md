# Day 02：可靠的模型客户端（PyCharm 实践版）

今天总投入 8 小时，但不固定理论、编码和测试分别占用多少时间。按下面的阶段推进：每完成一个检查点再进入下一阶段；遇到陌生概念时先暂停编码，把概念讲清楚，再回到代码验证。

## 今天的目标

昨天解决的是“程序能够调用模型”。今天解决的是“模型调用在正常、异常和格式不可靠的情况下，仍然给上层程序一个明确、稳定、可测试的结果”。

今天最终要能解释这条链路：

```text
项目内部 messages
  → DeepSeekClient 构造 HTTP 请求
  → DeepSeek/OpenAI 兼容 JSON 响应
  → 状态码与响应体检查
  → _normalize() 统一字段
  → Pydantic 校验
  → ModelReply / 明确的 LLMError
```

## 今天必须交付

- [ ] 逐行读懂 `DeepSeekClient.complete()`、`_normalize()` 和 `complete_json()`。
- [ ] 完成一张“供应商响应字段 → 项目内部字段”的映射表。
- [ ] 为正常文本、工具调用、缺失字段、非法工具 JSON、结构化输出、429、400 和超时补测试。
- [ ] 验证临时错误会有限重试，永久错误不会盲目重试。
- [ ] 编写 `examples/day02_structured_output.py`，用 Pydantic 校验结构化输出。
- [ ] 上层测试不依赖真实 DeepSeek API，不消耗 API 费用。
- [ ] 完成 `curriculum/day-02-log.md`。
- [ ] 确认 `.env` 没有进入 Git，并提交 Day 02 成果。

## 今天涉及的文件

| 文件 | 用途 | 今天是否修改 |
|---|---|---|
| `src/research_agent/llm.py` | HTTP 请求、重试、响应规范化和结构化输出 | 根据测试结果小幅修改 |
| `src/research_agent/models.py` | `ModelReply`、`ToolCall`、`Usage` 数据模型 | 以阅读为主 |
| `src/research_agent/config.py` | API Key、模型、Base URL 和超时配置 | 以阅读为主 |
| `tests/test_llm.py` | 模型客户端单元测试 | 核心修改文件 |
| `examples/day02_structured_output.py` | Pydantic 结构化输出实验 | 新建 |
| `curriculum/day-02-log.md` | 今日理解、错误、测试和费用记录 | 新建 |

## 阶段 0：补齐开始条件

项目当前状态：

- `.env` 已存在。
- `examples/day01_api_probe.py` 已存在。
- `tests/test_llm.py` 当前有 2 个测试并全部通过。
- 项目当前还不是 Git 仓库。
- `curriculum/day-01-log.md` 当前不存在。

先在 PyCharm Terminal 中执行：

```powershell
python --version
python -c "import sys; print(sys.executable)"
python -m pytest tests/test_llm.py -q
```

预期：

```text
Python 3.11.16
E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe
2 passed
```

如果还没有初始化 Git，执行：

```powershell
git init
git status
```

确认 `git status` 中没有 `.env` 和 `.venv`。Day 1 日志可以简短补写，但不要因此阻塞 Day 02 的核心实验。

### 检查点

- PyCharm 使用项目 `.venv`。
- `tests/test_llm.py` 的原有 2 个测试通过。
- `.env` 没有进入 Git 待提交列表。

## 阶段 1：建立可靠客户端的心智模型

打开以下三个文件并并排查看：

1. `src/research_agent/config.py`
2. `src/research_agent/llm.py`
3. `src/research_agent/models.py`

按下面的问题阅读代码。

### 1. 配置从哪里来

在 `Settings` 中找到：

```text
deepseek_api_key
deepseek_base_url
deepseek_model
request_timeout_seconds
```

能够说明：配置对象只负责保存运行参数，HTTP 客户端负责使用这些参数，两者职责不同。

### 2. 请求怎样构造

在 `DeepSeekClient.complete()` 中找到：

```text
payload
headers
AsyncClient
client.post()
response.raise_for_status()
response.json()
```

自己在日志中写出一个脱敏后的请求示例：

```json
{
  "model": "deepseek-chat",
  "messages": [
    {"role": "user", "content": "解释什么是 JSON"}
  ],
  "temperature": 0.1
}
```

不要把真实 `Authorization` 内容写入日志。

### 3. 响应为什么要规范化

供应商返回的是字典；项目其他模块使用的是：

```text
ModelReply
├── content
├── tool_calls
├── usage
└── request_id
```

今天需要理解：`_normalize()` 是外部数据与项目内部类型之间的边界。以后即使更换供应商，上层 Agent 仍然只依赖 `ModelReply`。

### 4. 错误分成哪几类

先不要急着写代码，在 `day-02-log.md` 中建立下面的分类：

| 类别 | 例子 | 通常是否重试 | 原因 |
|---|---|---:|---|
| 配置错误 | 缺少 API Key | 否 | 重试不会生成密钥 |
| 网络临时错误 | 超时、连接中断 | 是，次数有限 | 下一次可能恢复 |
| HTTP 临时错误 | 429、500、502、503、504 | 是，次数有限 | 限流或服务短暂异常 |
| HTTP 永久错误 | 400、401、403、404 | 否 | 请求或权限需要修改 |
| 响应格式错误 | 缺少 `choices`、非法 JSON | 通常否 | 返回内容不符合契约 |
| 业务空结果 | `content` 为空但存在工具调用 | 不一定是错误 | 可能是在请求执行工具 |

### 检查点

不看代码，能口头解释：

1. 为什么不能让 `MiniAgent` 到处读取 `response["choices"][0]`？
2. 为什么 429 可以重试，而 401 不应该重试？
3. 为什么“HTTP 200”仍然可能产生响应格式错误？
4. 为什么重试必须有最大次数？

## 阶段 2：用 PyCharm 调试一次规范化

打开 `tests/test_llm.py`，在现有测试中设置断点：

- 调用 `DeepSeekClient._normalize(...)` 的位置。
- `llm.py` 中读取 `choices[0]["message"]` 的位置。
- 创建 `ToolCall` 的位置。
- 创建 `Usage` 和 `ModelReply` 的位置。

右键第一个测试，选择“调试”。依次观察：

```text
data
message
raw
function
arguments
raw_usage
reply
```

特别观察 `function.arguments`：供应商返回的是 JSON 字符串，项目内部最终得到的是 Python 字典。

### 必须完成的字段映射表

把下表复制到 `day-02-log.md` 并填写“转换规则”：

| 外部响应字段 | 项目内部字段 | 类型 | 转换规则 |
|---|---|---|---|
| `id` | `ModelReply.request_id` | `str \| None` | |
| `choices[0].message.content` | `ModelReply.content` | `str` | |
| `message.tool_calls[]` | `ModelReply.tool_calls` | `list[ToolCall]` | |
| `function.name` | `ToolCall.name` | `str` | |
| `function.arguments` | `ToolCall.arguments` | `dict` | |
| `usage.prompt_tokens` | `Usage.prompt_tokens` | `int` | |
| `usage.completion_tokens` | `Usage.completion_tokens` | `int` | |
| `usage.total_tokens` | `Usage.total_tokens` | `int` | |
| 本地计时结果 | `Usage.elapsed_seconds` | `float` | |

### 检查点

- 能解释序列化和反序列化。
- 能解释为什么 JSON 字符串不能直接当 Python 字典使用。
- 能解释 Pydantic 在 `ModelReply` 构造过程中提供了什么保护。

## 阶段 3：补齐纯响应解析测试

先只测试 `_normalize()`，不发送网络请求。继续在 `tests/test_llm.py` 中添加以下案例：

1. **普通文本响应**
   - `content` 正确进入 `ModelReply.content`。
   - 没有工具调用时 `tool_calls == []`。
   - Token 和请求 ID 正确映射。

2. **合法工具参数**
   - `arguments` 是 JSON 字符串时，被解析成 Python 字典。

3. **非法工具参数 JSON**
   - 示例：`"{not-json}"`。
   - 必须抛出 `LLMResponseError`。

4. **缺少关键响应字段**
   - `{}`、空的 `choices`、没有 `message`。
   - 必须得到清楚的 `LLMResponseError`，不能泄漏难懂的 `KeyError`。

5. **缺少 usage**
   - 应使用 0 作为默认 Token，而不是崩溃。

6. **content 为 null 但存在工具调用**
   - `content` 应规范化为空字符串。
   - 工具调用必须保留下来。

每写完一个测试立即运行，不要一次写完全部再排错。

### PyCharm 运行方式

右键单个测试函数运行；单个通过后，再右键 `tests/test_llm.py` 运行整个文件。

### 检查点

- 纯 `_normalize()` 测试不访问网络。
- 每个测试只验证一种明确行为。
- 所有失败信息都能说明违反了哪个数据契约。

## 阶段 4：使用 respx 测试 HTTP 与重试

这一阶段使用项目已经安装的 `respx` 模拟 HTTP 服务。测试不会调用真实 DeepSeek，也不会产生费用。

先理解三层关系：

```text
pytest：组织测试和断言
respx：拦截 httpx 请求并返回预设结果
DeepSeekClient：以为自己正在访问真实 HTTP 服务
```

在 `tests/test_llm.py` 中导入：

```python
import httpx
import respx

from research_agent.config import Settings
from research_agent.llm import DeepSeekClient, LLMError
```

创建测试用配置时使用假密钥：

```python
settings = Settings(
    deepseek_api_key="test-key-not-real",
    deepseek_base_url="https://api.deepseek.com",
    request_timeout_seconds=0.1,
)
```

必须实现以下测试：

### A. HTTP 200 正常文本

- Mock `/chat/completions` 返回合法响应。
- 调用 `await client.complete(...)`。
- 断言得到 `ModelReply`。
- 断言实际请求 JSON 包含 `model` 和 `messages`。

### B. 429 后成功

- 第一次返回 429。
- 第二次返回合法 200。
- 断言最终成功。
- 断言路由被调用 2 次。

### C. 429 持续失败

- 所有尝试都返回 429。
- 设置 `retries=2` 时，总请求次数应为 3。
- 最终必须抛出明确的 `LLMError`。

### D. 400 不重试

- 返回 400。
- 断言只调用 1 次。
- 解释为什么修改请求比重复发送更有意义。

### E. 网络超时

- 让 Mock 抛出 `httpx.ReadTimeout`。
- 设置 `retries=2`，断言总请求次数为 3。
- 最终错误必须明确表明模型调用失败。

### F. HTTP 200 但响应体不是合法 JSON

- 返回普通文本而不是 JSON 对象。
- 观察当前实现产生什么异常。
- 如果异常不是项目自己的 `LLMResponseError`，先写一个失败测试，再最小修改 `llm.py`。

### 修改生产代码的规则

只有测试暴露出问题时才修改 `src/research_agent/llm.py`：

1. 先看到测试失败。
2. 写下失败原因。
3. 做满足测试的最小修改。
4. 重新运行单个测试。
5. 再运行整个 `tests/test_llm.py`。

不要为了“看起来更完整”一次重写整个客户端。

### 检查点

- Mock 测试运行时不需要真实 `.env` API Key。
- 能用 `route.call_count` 证明发生了几次请求。
- `retries=2` 的含义是首次调用后最多再试 2 次，总计最多 3 次。
- 400、401 等永久错误不会等待后继续发送同样请求。

## 阶段 5：练习 Pydantic 结构化输出

新建 `examples/day02_structured_output.py`。

先定义模型：

```python
from pydantic import BaseModel, Field


class ConceptExplanation(BaseModel):
    concept: str
    explanation: str
    confidence: float = Field(ge=0, le=1)
```

然后使用：

```python
await client.complete_json(messages, ConceptExplanation)
```

提示模型只返回 JSON，并要求字段严格对应 `ConceptExplanation`。

至少验证三种情况：

1. 合法 JSON：成功得到 `ConceptExplanation` 对象。
2. JSON 语法错误：抛出结构化输出错误。
3. JSON 合法但字段错误，例如缺少 `confidence` 或置信度为 `1.5`：Pydantic 拒绝。

前两个异常案例优先用 Mock 测试。真实 DeepSeek 最多运行一次成功案例，用于确认端到端链路，不要反复消耗 API。

### PyCharm 运行配置

| 配置项 | 值 |
|---|---|
| 名称 | `Day02 Structured Output` |
| 脚本路径 | `examples/day02_structured_output.py` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | `Python 3.11 (agent-learning-lab)` |

### 检查点

- 能区分“JSON 语法合法”和“数据符合 Schema”。
- 能解释 `model_validate_json()` 同时完成反序列化和字段校验。
- 上层代码拿到的是项目定义的 Pydantic 对象，而不是随意结构的字典。

## 阶段 6：整理错误模型与费用记录

检查当前异常：

```text
LLMError
├── LLMConfigurationError
└── LLMResponseError
```

根据测试结果判断是否还需要让 HTTP/网络错误携带更明确的信息。最低要求是错误信息可以回答：

- 失败发生在配置、网络、HTTP 还是响应解析阶段？
- 如果是 HTTP，状态码是什么？
- 是否已经用完有限重试次数？
- 日志是否完全不包含 API Key？

`Usage` 已经包含：

```text
prompt_tokens
completion_tokens
total_tokens
model_calls
estimated_cost
elapsed_seconds
```

今天核心要求是 Token 和耗时可靠记录。费用估算应使用可配置的输入、输出单价，并注明单价来源日期；不要凭记忆硬编码价格。来不及完成费用计算时，把它保留为扩展任务，不影响错误处理与测试主线。

## 阶段 7：运行验证

先运行 Day 02 的目标测试：

```powershell
python -m pytest tests/test_llm.py -q
```

再运行完整回归：

```powershell
python -m pytest -q
```

如果完整回归因为系统临时目录权限失败，而 `tests/test_llm.py` 全部通过，应先记录为环境问题，不要错误地修改业务代码。可以在 PyCharm 运行配置中把临时目录设置到项目内可写目录后重试：

```text
TEMP=E:\agent_project\agent-learning-lab\.tmp
TMP=E:\agent_project\agent-learning-lab\.tmp
```

并把 `.tmp/` 加入 `.gitignore`。只有实际遇到该权限问题时才做这一步。

### 回归检查

- 不调用真实 API 的单元测试应快速、稳定、可重复。
- 测试输出和失败信息中没有 API Key。
- 原来的离线 Agent 测试仍然通过。
- 新的异常处理没有破坏 `MiniAgent`。

## 阶段 8：完成 Day 02 日志与 Git 提交

复制日志模板：

```powershell
Copy-Item curriculum\daily-log-template.md curriculum\day-02-log.md
```

日志至少包含：

1. “供应商响应 → ModelReply”字段映射表。
2. 六类错误的分类与是否重试。
3. 一个失败测试的最小复现、根因和修复。
4. `tests/test_llm.py` 的最终测试结果。
5. 真实 API 调用次数、Token、耗时和费用；没有真实调用则写 0。
6. 当前还解释不清的问题。

提交前执行：

```powershell
git status
git diff --check
python -m pytest tests/test_llm.py -q
```

确认没有 `.env` 后提交：

```powershell
git add src/research_agent/llm.py tests/test_llm.py examples/day02_structured_output.py curriculum/day-02-log.md curriculum/day-02-pycharm.md
git status
git commit -m "test: harden model client behavior"
```

如果你最终没有修改 `llm.py`，从 `git add` 命令中删除该路径即可。

## 有余力再做的扩展任务

核心任务完成后再选择：

1. 为不同 OpenAI 兼容供应商增加相同测试，验证上层接口不变化。
2. 保存响应中的供应商请求 ID，研究它对排查服务端问题的价值。
3. 实现可配置的输入与输出 Token 单价，计算 `estimated_cost`。
4. 给重试增加可注入的等待函数，使测试无需真的等待退避时间。
5. 比较 `BaseModel.model_validate()`、`model_validate_json()` 和普通 `json.loads()`。

## 今日最终验收标准

Day 02 只有在以下条件全部满足时才算完成：

1. 能不看代码说明 `complete()`、`_normalize()` 和 `complete_json()` 各自负责什么。
2. 普通文本和合法工具调用能得到稳定的 `ModelReply`。
3. 缺失字段、非法工具参数 JSON 和不符合 Schema 的输出会产生清楚错误。
4. 429 与超时会有限重试，400 不会盲目重试。
5. 所有错误路径都没有无限循环。
6. Mock 测试不会访问真实 DeepSeek，不产生 API 费用。
7. 上层代码不依赖 DeepSeek 的原始字典结构。
8. 完成字段映射表、测试证据和学习日志。
9. `.env` 未进入版本控制，并完成 Git 提交。

## 口头验收题

学习结束后，不看笔记回答：

1. 为什么 HTTP 200 不等于模型响应一定可用？
2. Schema、JSON 和 Pydantic 模型分别解决什么问题？
3. 序列化与反序列化分别发生在哪里？
4. `retries=2` 最多会发出几次请求？
5. 哪些错误适合重试，哪些错误重试没有意义？
6. 为什么项目内部应该使用 `ModelReply`，而不是直接传递供应商 JSON？
7. Mock HTTP 与 Mock 模型有什么区别？
8. 如何证明测试没有产生真实 API 费用？

如果其中任何一题只能背定义、无法结合项目代码说明，就回到对应阶段重新运行断点或最小测试。
