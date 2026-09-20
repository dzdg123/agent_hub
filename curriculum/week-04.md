# 第 4 周：MCP 与 GPT Researcher

## Day 16：MCP Server

- 核心：阅读 `mcp_server.py`；运行 Server；使用测试 Client 调用 health、list 和 search。
- 必须提交：Host、Client、Server 图和一次 JSON-RPC 调用说明。
- 口头检查：MCP Server 为什么通常不等于 Agent？
- 扩展：增加一个 Resource 和 Prompt。

## Day 17：MCP 安全边界

- 核心：测试目录越界、localhost、私网、非 HTTP URL、错误参数、超大结果和超时。
- 必须提交：安全测试表。
- 口头检查：为什么远程 MCP Server 的工具描述也属于不可信输入？
- 扩展：增加只读工具审计日志。

## Day 18：MCP Client

- 核心：实现并测试工具发现、工具选择、调用、结果回传和 Server 离线降级。
- 必须提交：MCP 与 Function Calling 的职责对照表。
- 口头检查：模型知道一个工具存在，是因为哪一层把描述交给了它？
- 扩展：同时连接两个 Server。

## Day 19：GPT Researcher 主流程

- 核心：从 `GPTResearcher.conduct_research()` 跟踪到 ResearchConductor、Retriever、ContextManager、Writer。
- 必须提交：`query → context → report` 调用链。
- 口头检查：为什么 `GPTResearcher` 更像协调器？
- 扩展：跟踪费用和日志回调。

## Day 20：GPT Researcher MCP 链路

- 核心：跟踪 MCPRetriever、MCPClientManager、MCPToolSelector、MCPResearchSkill；分析 fast、deep、disabled。
- 必须提交：与本项目 MCP 实现的差异表和 Agent v2 标签。
- 口头检查：哪些是 MCP 标准，哪些是 GPT Researcher 自己的策略？
- 扩展：运行仓库 MCP 局部测试。

