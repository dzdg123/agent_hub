# 第 3 周：LangGraph 工作流

本周代码范围：`workflow.py`、`models.py`、`storage.py`、`events.py`。

## Day 11：StateGraph

- 核心：完成官方 Quickstart；阅读 `ResearchState` 和 `build_langgraph()`；把研究流程拆成 plan、retrieve、curate、write、validate 节点。
- 必须提交：节点输入输出表和状态图。
- 口头检查：State 与普通局部变量的关键区别是什么？
- 扩展：比较 Graph API 与 Functional API。

## Day 12：研究计划

- 核心：完善结构化 `ResearchPlan`；测试简单问题、复杂问题、重复子问题和坏 JSON。
- 必须提交：10 个问题及计划质量点评。
- 口头检查：什么问题不值得拆分？
- 扩展：加入子问题依赖关系。

## Day 13：并行检索

- 核心：跟踪 Semaphore、`gather` 和 `merge_ranked`；模拟一个分支失败。
- 必须提交：并行执行时序图和失败隔离证据。
- 口头检查：并发写共享状态会产生什么问题？
- 扩展：按子问题类型选择 Retriever。

## Day 14：循环、检查点与停止

- 核心：把证据充分性改为独立节点；确保补充检索最多两轮；验证 SQLite 恢复和取消。
- 必须提交：所有终止路径清单。
- 口头检查：一个 Agent 为什么必须具有硬停止条件？
- 扩展：恢复时跳过已完成工具。

## Day 15：Agent v1

- 核心：分别完成一次纯网页、纯文档和混合研究；回归前两周测试。
- 必须提交：三份运行轨迹、本周架构图和复盘。
- 口头检查：从 query 到 report，数据经过哪些类型变化？
- 扩展：支持域名限制。

