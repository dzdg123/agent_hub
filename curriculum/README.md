# 6 周学习工作簿

每天投入总计 8 小时，阅读、实验、编码和测试按实际难度动态调整。不要按时间机械切换；以当天的“必须提交”和“口头检查”作为结束条件。

## 使用方式

每天开始：

1. 阅读对应周文件中的当天目标。
2. 在 `notes/day-XX.md` 复制[日志模板](daily-log-template.md)。
3. 先运行现有测试，确认起点正常。
4. 完成核心任务并补充有意义的测试。
5. 回答当天口头检查问题，再提交 Git。

阻塞超过合理时间时，先写最小复现并缩小问题；当天只保证最小可运行成果，扩展项可以删除。周末只用于补核心验收，不新增课程内容。

## 进度表

- [ ] 第 1 周：[手写最小 Agent](week-01.md)
- [ ] 第 2 周：[搜索、文档与 RAG](week-02.md)
- [ ] 第 3 周：[LangGraph 工作流](week-03.md)
- [ ] 第 4 周：[MCP 与 GPT Researcher 源码](week-04.md)
- [ ] 第 5 周：[API、网页、可观测性和评估](week-05.md)
- [ ] 第 6 周：[结业项目打磨](week-06.md)

最终使用[结业验收清单](acceptance-checklist.md)逐项检查。

## 项目代码地图

| 学习主题 | 代码入口 |
|---|---|
| 模型接口 | `src/research_agent/llm.py` |
| Function Calling | `tools.py`、`mini_agent.py` |
| 文档加载 | `documents.py` |
| 混合检索 | `retrieval.py` |
| 网页检索 | `web.py` |
| 研究工作流 | `workflow.py` |
| MCP | `mcp_server.py` |
| API 与任务状态 | `api.py`、`storage.py` |
| 实时事件 | `events.py`、`static/app.js` |

