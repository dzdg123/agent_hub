# 第 1 周：手写最小 Agent

本周代码范围：`llm.py`、`tools.py`、`mini_agent.py`、`demo_model.py`。

## Day 1：环境和第一次模型调用

- 核心：安装 Python 3.11，创建虚拟环境，安装项目，复制 `.env.example`，运行 `research-agent demo`，再配置 DeepSeek 执行一次 `ask`。
- 阅读：README 的环境与安全部分、DeepSeek 官方首次调用文档。
- 必须提交：环境检查记录和一次脱敏后的请求用量。
- 口头检查：虚拟环境隔离了什么？API Key 为什么只能经环境变量进入程序？
- 扩展：用不同 system 消息运行相同问题并记录差异。

## Day 2：可靠模型客户端

- 核心：逐行阅读 `DeepSeekClient.complete()` 和 `_normalize()`；为缺少字段、非法工具 JSON、429 和超时补测试。
- 必须提交：一张“网络响应 → ModelReply”的字段映射表。
- 口头检查：为什么项目内部不能到处使用供应商原始响应？哪些错误值得重试？
- 扩展：给用量增加自定义价格估算器。

## Day 3：异步与并发

- 核心：在 `examples/async_lab.py` 自己实现串行、`gather`、Semaphore 和单任务失败实验。
- 必须提交：运行耗时对比和失败隔离测试。
- 口头检查：协程、Task 和线程有什么区别？为什么 I/O 并发能缩短等待？
- 扩展：使用 Python 3.11 `TaskGroup` 重写。

## Day 4：工具系统

- 核心：阅读 `Tool`、`ToolRegistry`、`safe_calculate`；增加一个只读工具并为参数错误补测试。
- 必须提交：工具 Schema、调用输入和调用结果三个 JSON 示例。
- 口头检查：模型选择工具与程序执行工具的边界在哪里？
- 扩展：支持一轮并行执行多个只读工具。

## Day 5：Mini Agent v0

- 核心：给 `MiniAgent` 增加至少 15 个固定案例，覆盖普通回答、工具调用、未知工具、缺参、取消和最大步数。
- 必须提交：Agent 循环图、测试结果和本周复盘。
- 口头检查：一次工具结果为什么要作为 `tool` 消息再次发送给模型？
- 扩展：在 CLI 中逐步打印 RunEvent。

