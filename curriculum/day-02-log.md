# Day 02 学习日志：可靠的模型客户端

> 2026-09-19 根据已有笔记、当前实现和本次本地测试补记。保留原有错误分类，补齐字段映射，并纠正响应转换过程。历史真实 API 数据待补。

## 核心理解

`complete()` 构造 payload 和 headers，通过 `client.post(json=payload)` 发送请求，检查状态码并处理有限重试。`response` 是 HTTP 响应对象；`response.json()` 才把响应体解析为 Python 数据；`_normalize()` 再把这些数据转换为 `ModelReply`，并不是把 HTTP 响应转换为字典。

`_normalize()` 隔离供应商字段结构，让上层 Agent 使用统一的 `content`、`tool_calls`、`usage`、`request_id`。

`complete_json()` 请求 JSON 输出，再用 `schema.model_validate_json(reply.content)` 解析并校验内容。JSON 语法合法不代表字段满足要求，例如 `confidence=1.5` 不符合 0～1 的约束。HTTP 200 也不保证响应 JSON 或业务字段正确。

## 错误分类与重试

| 类别        | 例子                   | 通常是否重试 | 原因         |
| --------- | -------------------- | -----: | ---------- |
| 配置错误      | 缺少 API Key           |      否 | 重试不会生成密钥   |
| 网络临时错误    | 超时、连接中断              | 是，次数有限 | 下一次可能恢复    |
| HTTP 临时错误 | 429、500、502、503、504  | 是，次数有限 | 限流或服务短暂异常  |
| HTTP 永久错误 | 400、401、403、404      |      否 | 请求或权限需要修改  |
| 响应格式错误    | 缺少 `choices`、非法 JSON |    通常否 | 返回内容不符合契约  |
| 业务空结果     | `content` 为空但存在工具调用  | 不一定是错误 | 可能是在请求执行工具 |


| 外部响应字段                       | 项目内部字段                    | 类型               | 转换规则 |
| ---------------------------- | ------------------------- | ---------------- | ---- |
| `id`                         | `ModelReply.request_id`   | `str \| None`    | `data.get("id")`，缺失时为 `None` |
| `choices[0].message.content` | `ModelReply.content`      | `str`            | 缺失、null 或空值统一为空字符串 |
| `message.tool_calls[]`       | `ModelReply.tool_calls`   | `list[ToolCall]` | 缺失或 null 时用空列表，否则逐项构造 `ToolCall` |
| `function.name`              | `ToolCall.name`           | `str`            | 读取名称，缺失时默认空字符串 |
| `function.arguments`         | `ToolCall.arguments`      | `dict`           | 字符串经 `json.loads()` 解析；缺失默认 `{}`，再由数据模型校验 |
| `usage.prompt_tokens`        | `Usage.prompt_tokens`     | `int`            | 缺失时默认 0 |
| `usage.completion_tokens`    | `Usage.completion_tokens` | `int`            | 缺失时默认 0 |
| `usage.total_tokens`         | `Usage.total_tokens`      | `int`            | 缺失时默认 0，当前实现不会自动求和补齐 |
| 本地计时结果                       | `Usage.elapsed_seconds`   | `float`          | `perf_counter()` 差值，包含此前重试及退避耗时 |

`retries=2` 表示首次请求加最多 2 次重试，总计最多 3 次。当前退避等待依次为 0.5 秒、1 秒。最后一次失败后不再等待重试。

异常层次为 `LLMError`、其子类 `LLMConfigurationError` 和 `LLMResponseError`。HTTP/网络最终失败抛出 `LLMError`；非法响应和结构化输出校验失败使用 `LLMResponseError`。

## 已实现的实验

- `examples/day02_structured_output.py` 定义 `ConceptExplanation`，含 `concept`、`explanation`、`confidence`，其中置信度限制为 0～1。
- 示例通过 `complete_json()` 请求解释反序列化，打印校验后的字段；本次未运行这个真实 API 示例。
- `tests/test_llm.py` 使用 `respx` 拦截 HTTP 请求，以假密钥和预设响应验证客户端，不需要真实 DeepSeek 服务。

## 本次测试证据与实际覆盖

工作目录为项目根目录，执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm.py tests/test_mini_agent.py tests/test_tools.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_llm.py --collect-only -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp E:\agent_project\day123-verification-20260919-a
```

结果：相关模块 **17 passed, 1 warning in 3.34s**；LLM 文件实际收集 **9 个测试**；完整回归 **32 passed, 1 warning in 4.22s**。相关模块警告是 pytest 缓存写入权限问题；完整回归警告是第三方弃用提示。

| 当前有效案例 | 验证内容 |
|---|---|
| 合法工具响应 | 参数 JSON 字符串转字典，Token 映射 |
| HTTP 200 | 返回文本，调用 1 次 |
| 持续 429 | 重试耗尽后报错，调用 3 次 |
| HTTP 400 | 直接失败，仅调用 1 次 |
| ReadTimeout | 重试耗尽后报错，调用 3 次 |
| HTTP 200 但响应不是 JSON | 抛出 `LLMResponseError`，调用 1 次 |
| 结构化内容 JSON 不合法 | 结构化输出校验失败 |
| 置信度为 1.5 | Schema 校验失败 |
| 缺少 message 路径 | 抛出 `LLMResponseError` |

## 错误与待修复问题

| 问题 | 根因或证据 | 修复方向与状态 |
|---|---|---|
| 误以为 `_normalize()` 把 HTTP 响应转成字典 | 混淆 HTTP 对象、JSON 解析和内部模型 | 本日志已修正职责说明 |
| “429 后成功”测试没有实际运行 | 两个函数都叫 `test_complete_retries_after_429_then_succeeds`，后一个持续失败案例覆盖前一个 | 待给持续失败案例改名，再分别验证 2 次成功、3 次失败 |
| 部分 Mock 测试使用错误的 messages 结构 | 持续 429 传字符串列表，400 传单个字典；Mock 仍返回预设状态，未验证请求契约 | 待统一为 `[{"role": "user", "content": "你好"}]` 并检查请求体 |
| 400 案例名称含 then_succeeds，但实际断言失败 | 名称与测试意图不符 | 待改名为明确的“不重试”案例 |

当前源码已包含非法响应 JSON 的异常转换，但没有保存“修改前失败、修改后通过”的历史输出，因此不把该过程描述为本次亲历的修复。

## 未完成项

- [ ] 修复同名测试覆盖问题，补请求体断言。
- [ ] 补非法工具参数 JSON、空 choices、缺少 message、缺少 usage、content 为 null 且含工具调用等独立案例。
- [ ] 补合法结构化输出成功案例，与已有两类拒绝案例配套。
- [ ] 补真实结构化输出示例的脱敏运行证据（若历史上已运行，优先补历史记录）。
- [ ] 完成 Git 提交；本次检查仓库尚无提交。

## 成本记录与复习问题

本次复核只运行 Mock、离线 Demo 与本地异步模拟，新增真实 API 调用 0 次、费用 0 元。历史真实调用次数、Token、耗时与费用未知，不能写成 0。当前没有足够证据填写实际费用估算。

复习时应能说明：序列化与反序列化发生在哪里；HTTP 成功为何仍可能校验失败；为什么重试次数必须有限；Mock HTTP 验证客户端请求处理，Mock 模型验证上层 Agent 控制流程。笔记整理不代替独立口头验收。
