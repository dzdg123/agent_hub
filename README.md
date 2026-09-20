# Agent Learning Lab

这是一个配套 6 周、240 小时学习计划的研究型 Agent 项目。它从手写工具循环开始，逐步加入网页与本地文档检索、引用、LangGraph、MCP、FastAPI、SSE、持久化和评估。

## 你会实现什么

最终数据流：

```text
问题 -> 研究计划 -> 人工确认 -> 并行检索 -> 证据整理
     -> 证据缺口检查 -> 补充检索（最多两轮）-> 带引用报告
```

项目包含：

- DeepSeek OpenAI 兼容客户端，支持超时、重试、结构化输出和用量记录。
- 不依赖框架的工具调用 Agent，方便理解模型与工具的边界。
- TXT、Markdown、PDF 文档加载和可测试的本地混合检索。
- LangGraph 研究工作流入口以及无模型 Mock 工作流。
- 只读 MCP Server：文档列表、文档检索、网页获取和来源读取。
- FastAPI 任务接口、SSE 进度、取消、SQLite 存储和简单网页。
- 单元、集成与评估示例。
- `curriculum/` 中按 6 周组织的学习指南和验收清单。

## 环境安装

确认使用 Python 3.11：

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

向量扩展是可选项。前两周先使用项目内置的确定性向量实现，理解流程后再安装：

```powershell
pip install -e ".[dev,vector]"
```

复制配置并填写自己的密钥：

```powershell
Copy-Item .env.example .env
```

密钥也可以仅在当前终端设置：

```powershell
$env:DEEPSEEK_API_KEY="你的密钥"
```

## 快速运行

不使用真实 API 的演示：

```powershell
research-agent demo
```

使用 DeepSeek：

```powershell
research-agent ask "计算 12 * 8，然后统计结果有几个字符"
```

启动网页与 API：

```powershell
research-agent-api
```

打开 <http://127.0.0.1:8000>，API 文档位于 <http://127.0.0.1:8000/docs>。

启动 MCP Server：

```powershell
research-mcp
```

运行测试：

```powershell
pytest
```

## 学习入口

从 [课程总览](curriculum/README.md) 开始。每一天都包含核心任务、扩展任务、验收问题和一个可提交成果。每天只固定总计 8 小时，具体时间由当天的理解和调试情况决定。

## 安全边界

- MCP 文件工具只能访问 `DOCUMENT_ROOT`。
- 网页抓取拒绝本机、私网和非 HTTP(S) 地址。
- 上传文件限制为 TXT、Markdown 和 PDF。
- API Key 不会写入数据库、报告或运行日志。
- 取消任务后，工作流会在下一个节点边界停止。

## 当前定位

这是教学与作品集项目。任务存储和后台执行位于单进程内，适合本地学习与演示。多进程队列、分布式锁、用户认证和生产部署属于后续扩展。

