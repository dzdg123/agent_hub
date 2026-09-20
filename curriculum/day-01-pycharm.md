# Day 1：在 PyCharm 中完成环境验证与第一次模型调用

今天只固定总投入 8 小时，不规定每一阶段的小时数。完成一个阶段的检查点后再进入下一阶段；如果提前完成，做最后的扩展实验。

## 今天必须交付

- [ ] PyCharm 使用项目 `.venv` 中的 Python 3.11.16。
- [ ] 全部测试运行通过，并保存脱敏后的测试结果。
- [ ] 离线 Demo 能完成一次模型选择工具、Python 执行工具、模型返回答案的循环。
- [ ] `examples/day01_api_probe.py` 能完成一次真实 DeepSeek 调用。
- [ ] 记录模型名称、请求 ID、Token 用量和请求耗时。
- [ ] 完成 `curriculum/day-01-log.md`。
- [ ] 初始化 Git，确认 `.env` 没有进入版本控制，然后完成当天提交。

## 阶段 1：确认 PyCharm 项目环境

### 操作

1. 用 PyCharm 打开 `E:\agent_project\agent-learning-lab`。
2. 检查右下角解释器，应为 `Python 3.11 (agent-learning-lab)`。
3. 打开 PyCharm Terminal，执行：

   ```powershell
   python --version
   python -c "import sys; print(sys.executable)"
   ```

4. 预期结果：

   ```text
   Python 3.11.16
   E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe
   ```

5. 在项目树中右键 `tests`，选择 `运行 pytest in tests`。

### 检查点

- Python 路径必须指向当前项目的 `.venv`。
- 测试结果应为 `25 passed`；当前第三方库警告不影响 Day 1。

### 需要理解

- PyCharm 项目解释器决定运行按钮使用哪个 Python。
- `.venv` 隔离的是解释器关联的软件包和命令，不会复制项目代码。
- `pyproject.toml` 声明项目依赖和支持的 Python 版本。

## 阶段 2：认识今天涉及的文件

按顺序阅读，不要求一次看懂整个项目：

1. `pyproject.toml`：找到 `requires-python`、`dependencies` 和 `[project.scripts]`。
2. `.gitignore`：确认 `.env` 和 `.venv/` 已被忽略。
3. `.env.example`：理解它只保存变量名称和安全的默认值。
4. `src/research_agent/config.py`：找到 `Settings` 如何读取 `.env`。
5. `src/research_agent/cli.py`：找到 `demo` 与 `ask` 如何选择不同模型。

阅读后，尝试口头回答：

- 为什么项目要求 Python 3.11，而 PyCharm 安装了什么版本并不重要？
- `.env.example` 和 `.env` 的用途有什么区别？
- 为什么 API Key 不能直接写在 `llm.py` 中？

## 阶段 3：运行离线 Demo

### 创建运行配置

进入 `运行 → 编辑配置`，添加 Python 配置：

| 项目 | 值 |
|---|---|
| 名称 | `Day01 Offline Demo` |
| 运行方式 | 模块名称 |
| 模块名称 | `research_agent.cli` |
| 参数 | `demo` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | `Python 3.11 (agent-learning-lab)` |

运行后预期看到工具执行结果 `96`，以及模型调用次数、工具调用次数和 Token 数。

### 使用调试器观察调用链

在以下位置设置断点：

1. `src/research_agent/cli.py` 中 `_execute()` 选择 `DemoModel` 的位置。
2. `src/research_agent/mini_agent.py` 中 `reply = await self.model.complete(...)`。
3. `src/research_agent/mini_agent.py` 中 `result = await self.tools.invoke(...)`。
4. `src/research_agent/tools.py` 中 `return await tool.invoke(arguments)`。

点击“调试”运行，用“步过”观察：

```text
prompt
  → messages
  → model.complete()
  → ModelReply.tool_calls
  → ToolRegistry.invoke()
  → ToolResult
  → tool 消息加入 messages
  → model.complete()
  → 最终文本答案
```

不要试图在今天理解每个类的全部细节。今天只需抓住模型负责提出调用意图，Python 负责真正执行函数。

### 检查点

- 能指出第一次 `ModelReply` 为什么没有直接返回最终答案。
- 能在调试器中找到 `calculator` 和参数 `12 * 8`。
- 能看到工具结果被作为 `role="tool"` 的消息加入上下文。

## 阶段 4：配置 DeepSeek

1. 在项目根目录复制 `.env.example`，将副本命名为 `.env`。
2. 填写自己的 `DEEPSEEK_API_KEY`。
3. 保留以下配置：

   ```dotenv
   DEEPSEEK_BASE_URL=https://api.deepseek.com
   DEEPSEEK_MODEL=deepseek-chat
   REQUEST_TIMEOUT_SECONDS=60
   ```

4. 不要把 `.env` 内容打印到控制台，不要在调试器截图中展开请求头的 `Authorization`。

检查 PyCharm 是否把 `.env` 显示为被 Git 忽略的文件。稍后还要使用 `git status` 再确认一次。

## 阶段 5：手写第一次 API 探针

在 `examples` 上右键，选择 `新建 → Python 文件`，创建 `day01_api_probe.py`。建议自己逐行输入以下代码：

```python
import asyncio

from research_agent.config import get_settings
from research_agent.llm import DeepSeekClient


async def main() -> None:
    settings = get_settings()
    client = DeepSeekClient(settings)

    reply = await client.complete(
        [
            {"role": "system", "content": "你是一名耐心的 Python 入门老师。"},
            {"role": "user", "content": "请用两句话解释 API 是什么。"},
        ]
    )

    print(f"模型: {settings.deepseek_model}")
    print(f"请求 ID: {reply.request_id}")
    print(f"回答: {reply.content}")
    print(f"输入 Token: {reply.usage.prompt_tokens}")
    print(f"输出 Token: {reply.usage.completion_tokens}")
    print(f"总 Token: {reply.usage.total_tokens}")
    print(f"耗时: {reply.usage.elapsed_seconds:.2f} 秒")


if __name__ == "__main__":
    asyncio.run(main())
```

### 调整运行配置

第一次右键运行后，进入 `运行 → 编辑配置`，把工作目录改为：

```text
E:\agent_project\agent-learning-lab
```

这是必要的，因为 `Settings` 从当前工作目录查找 `.env`。

### 观察真实请求

在 `src/research_agent/llm.py` 中设置两个断点：

1. `response = await client.post(...)`：执行前观察 `payload`，但不要展开或复制 `headers`。
2. `return self._normalize(...)`：执行后观察 HTTP 状态码与响应如何变成 `ModelReply`。

记录以下信息：

- 模型名称。
- 请求 ID。
- 输入、输出和总 Token。
- 请求耗时。
- 模型回答。

保存记录时不要包含 API Key 和完整请求头。

### 检查点

- 能解释 `messages` 为什么是列表，每个元素为什么有 `role` 和 `content`。
- 能说明 `payload` 怎样被 `httpx` 序列化为 JSON。
- 能说明 `await client.post(...)` 等待的是网络 I/O。
- 能指出 `_normalize()` 把供应商响应转换成项目自己的 `ModelReply`。

## 阶段 6：用自己的话画出一次请求

在 `curriculum/day-01-log.md` 中写出下面流程，并给每个箭头补一句解释：

```text
PyCharm 运行配置
  → Python 3.11 进程
  → Settings 读取 .env
  → DeepSeekClient 组装 payload 和请求头
  → httpx 发送 HTTPS 请求
  → DeepSeek API 处理 messages
  → HTTP JSON 响应
  → _normalize() 生成 ModelReply
  → 程序打印回答与 Usage
```

重点区分：

- API 是程序之间约定的交互接口。
- HTTP/HTTPS 是这次通信使用的协议。
- JSON 是请求体与响应体的数据格式。
- API Key 是服务器识别和授权调用者的凭证。
- Token 是模型处理文本时使用的计量单位之一。

## 阶段 7：完成学习日志

复制 `curriculum/daily-log-template.md` 为 `curriculum/day-01-log.md`，至少填写：

- 今天必须交付的内容。
- 虚拟环境与系统 Python 的区别。
- 离线 Demo 的调用链。
- 真实请求的模型、Token、耗时和请求 ID。
- 今天遇到的 PyCharm 解释器问题、根因和解决方式。
- 仍然解释不清的问题。

## 阶段 8：初始化 Git 并提交

项目目前还不是 Git 仓库。在 PyCharm Terminal 中执行：

```powershell
git init
git status
```

先检查 `git status`：输出中不能出现 `.env`、`.venv` 或 API Key。确认后执行：

```powershell
git add .
git status
git commit -m "chore: complete day 1 environment and API probe"
```

如果 Git 提示没有配置用户名和邮箱，只为当前项目配置：

```powershell
git config user.name "你的名字"
git config user.email "你的邮箱"
```

然后重新执行提交命令。

## 有余力再做的扩展任务

不要在核心任务未完成时做扩展。

1. 把 system 消息改成“你是一名严谨的技术文档作者”，使用相同 user 问题再次运行。
2. 比较两次回答的语气、结构、Token 和耗时。
3. 在日志中解释 system 消息改变了什么，没有改变什么。
4. 给 API 探针添加异常捕获，只显示错误类型，不打印 API Key 或请求头。

## 今日最终验收

只有以下条件全部满足，Day 1 才算完成：

1. PyCharm 和 Terminal 都使用项目的 Python 3.11.16。
2. `tests` 显示 25 个测试通过。
3. 离线 Demo 返回 96，并能通过断点讲清工具调用链。
4. 真实 DeepSeek 调用成功，记录了模型、请求 ID、Token 和耗时。
5. `.env` 不出现在 Git 待提交列表中。
6. `day-01-log.md` 能用自己的语言解释 API、HTTP、JSON、环境变量和虚拟环境。
7. 完成 Git 提交。

如果真实 API 因余额、网络或密钥问题暂时无法完成，应保存明确错误信息，其余核心任务继续完成；真实调用仍是进入 Day 2 前必须补齐的验收项。
