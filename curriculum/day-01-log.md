# Day 01 学习日志：环境、离线 Agent 与 API 调用

> 2026-09-19 根据当前代码与本次本地复核补记。下面的运行结果是本次复核结果，不代表 Day 01 当天的历史输出；真实 API 历史用量没有记录，不能补造。

## 学习目标与当前成果

- [x] 本次命令行使用项目 `.venv/Scripts/python.exe`，版本为 Python 3.11.16。
- [x] 本次完整测试通过：32 passed（当前版本，不沿用课程早期的 25 passed）。
- [x] 离线 Demo 完成模型提出工具调用、Python 执行工具、模型给出答案的循环。
- [x] 已有 `examples/day01_api_probe.py`，问题为“告诉我什么是装饰器”，会打印模型、请求 ID、回答、Token 和耗时。
- [ ] 真实 DeepSeek 成功调用的历史输出待补；仅有探针代码不能证明曾经调用成功。
- [ ] PyCharm 运行配置与断点操作未在本次复核中核实。
- [x] Git 已初始化，`.env` 被忽略且未被跟踪。
- [ ] 当前仓库尚无提交，不能把 Git 提交记为完成。

## 核心理解笔记

项目解释器决定运行代码时使用哪个 Python 和哪些依赖；终端是否激活虚拟环境与 PyCharm 的运行配置是两件事。`pyproject.toml` 声明 Python 版本范围、依赖和命令入口。

`.env.example` 提供配置示例，`.env` 保存本机实际配置。`Settings` 配置了相对路径 `.env`，因此从项目根目录运行有助于正确找到配置。API Key 不应写进源码或学习日志。

一次真实请求的路径：

```text
messages（Python 列表，包含 role 和 content）
→ complete() 构造 payload 和 headers
→ client.post(json=payload) 将请求数据序列化为 JSON 并发送
→ 检查 HTTP 状态码
→ response.json() 将响应 JSON 解析为 Python 数据
→ _normalize() 转换成项目内部的 ModelReply
→ 读取 content、usage 和 request_id
```

离线 Agent 的路径：

```text
用户问题 → DemoModel 提出 calculator 调用
→ ToolRegistry 执行 12 * 8 → 得到 96
→ 将工具结果作为 role="tool" 的消息加入上下文
→ 再次调用 DemoModel → 返回最终答案
```

模型提出工具名称和参数，Python 负责真正执行函数。工具结果必须回到消息列表，后续模型调用才能使用这个结果。

## 本次测试证据

工作目录：`E:\agent_project\agent-learning-lab`。

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m research_agent.cli demo
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp E:\agent_project\day123-verification-20260919-a
```

实际输出摘要：

```text
Python 3.11.16
工具执行完成：{"ok":true,"content":96.0,"error":null}
用量: 2 次模型调用, 1 次工具调用, 40 tokens
32 passed, 1 warning in 4.22s
```

Demo 的模型调用和 40 tokens 是本地模拟统计，不是 DeepSeek 的真实计费数据。完整测试中的警告来自 Starlette 使用已弃用的 AnyIO 别名，不影响本次通过结果。

本次相关模块检查曾出现 pytest 缓存目录拒绝访问警告；完整回归使用 `-p no:cacheprovider` 关闭缓存，使用上述独立临时目录存放测试文件。重跑时可选择新的可写临时目录。

Git 检查：`git check-ignore .env` 输出 `.env`；`git ls-files .env` 无输出；`git log -1` 提示当前分支尚无提交。

## 成本与性能

| 项目 | 记录 |
|---|---|
| 本次日志补全产生的真实 API 调用 | 0 次 |
| 本次新增 API 费用 | 0 元 |
| Day 01 历史真实调用次数、Token、耗时、费用 | 未保存可核实记录，待补 |
| 历史实际模型名称、请求 ID、回答 | 待从当时脱敏输出补充；配置默认值不能代替实际结果 |

## 后续补齐

补存一次真实探针的脱敏结果，核对 PyCharm 解释器和工作目录；能够结合代码解释消息、序列化、响应规范化和工具循环，再整理提交。以上理解笔记供复习使用，不等同于已经完成独立口头验收。
