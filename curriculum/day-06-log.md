# Day 06 学习日志：网页搜索、正文提取与批量抓取

日期：2026-10-12

## 当天完成的工作

- 阅读并梳理了“搜索结果 → 网页正文 → Agent 资料”的完整链路。
- 新增纯解析函数 `parse_search_html()`，将搜索 HTML 解析与 HTTP 请求分离。
- 新增纯解析函数 `extract_webpage()`，将正文提取与 HTTP 请求分离。
- 统一处理 DuckDuckGo 跳转链接、fragment、URL 去重和 `source_id`。
- 为搜索摘要和网页正文补充明确的 `metadata`。
- 完善搜索输入校验、空结果、验证码页和无法识别页面的处理。
- 完善正文请求的参数校验、Content-Type、404、超时和重定向处理。
- 新增 `collect_pages()`，支持去重、并发限制和单个失败隔离。
- 补齐不依赖互联网的搜索、正文、批处理和 URL 安全测试。
- 完善 `examples/day06_web_lab.py`，支持 `offline` 和 `live` 两种运行模式。
- 阅读 `workflow.py::_retrieve()`，理解网页资料进入研究 Agent 的位置。

## 完整链路与文件职责

```text
用户查询词
  ↓
DuckDuckGoHTMLSearch.search()
  ├─ 校验 query 和 max_results
  ├─ 发出搜索 HTTP 请求
  └─ 调用 parse_search_html()
       ↓
搜索 Source（search_snippet）
  ↓
collect_pages()
  ├─ URL 归一化和去重
  ├─ Semaphore 限制并发
  ├─ 对每个目标调用 fetch_webpage()
  └─ 分开保存成功正文和失败记录
       ↓
fetch_webpage()
  ├─ 校验 url、timeout、max_chars
  ├─ ensure_public_url() 检查公网地址
  ├─ 发出网页 HTTP 请求
  ├─ 检查状态码、重定向和 Content-Type
  └─ 调用 extract_webpage()
       ↓
正文 Source（web_page）
```

主要文件：

| 文件 | 职责 |
|---|---|
| `src/research_agent/web.py` | 搜索、URL 处理、正文提取、安全检查和批量抓取 |
| `src/research_agent/models.py` | 定义统一的 `Source` 数据模型 |
| `src/research_agent/workflow.py` | 将搜索摘要或完整正文接入研究工作流 |
| `tests/fixtures/day06/` | 保存固定 HTML 样例，保证测试可重复 |
| `tests/test_web_search.py` | 搜索解析、输入契约和搜索 HTTP 错误测试 |
| `tests/test_web_fetch.py` | 正文解析、HTTP wrapper 和批量抓取测试 |
| `tests/test_web_security.py` | 公网、私网和 DNS 混合结果测试 |
| `examples/day06_web_lab.py` | PyCharm 中运行 offline/live 实验的入口 |

## web.py 中各函数的职责

| 函数或类 | 作用 |
|---|---|
| `SearchProvider` | 定义搜索服务都要实现的异步 `search()` 接口 |
| `DuckDuckGoHTMLSearch.search()` | 负责搜索请求，不负责具体 HTML 解析 |
| `parse_search_html()` | 将搜索 HTML 字符串解析成 `list[Source]`，不联网 |
| `resolve_search_url()` | 解包跳转链接，保留原始目标，并生成去 fragment 的归一化 URL |
| `normalize_search_url()` | 只返回归一化 URL，供去重和批处理使用 |
| `validate_max_results()` | 限制搜索结果数为 1～10 的整数 |
| `extract_webpage()` | 从传入的 HTML 中提取标题和正文，不联网 |
| `validate_fetch_arguments()` | 在请求前检查 URL、timeout 和 max_chars |
| `ensure_public_url()` | 解析 DNS，拒绝本机、私网、回环和保留地址 |
| `fetch_webpage()` | 负责正文 HTTP 请求，再把响应交给 `extract_webpage()` |
| `collect_pages()` | 对候选 URL 去重、限并发抓取，并分别返回正文和失败记录 |

将“HTTP 请求”和“字符串解析”分开后，解析规则可以直接用 fixture 测试，不需要每次访问真实网站；网络错误和解析错误也更容易定位。

## 搜索摘要与网页正文的区别

搜索结果只包含搜索引擎展示的短摘要，不等于目标网页的完整正文。

搜索 Source 示例：

```text
title: 异步教程
url: https://example.org/article
content: 关于协程与等待的摘要。
source_id: web-9eba6b3c57ce169e
metadata:
  content_kind: search_snippet
  provider: duckduckgo_html
  original_url: https://example.org/article#intro
  truncated: false
```

对应正文 Source 示例：

```text
title: 异步学习笔记
url: https://example.org/article
content: 异步请求……多个独立请求可以并发推进。
source_id: web-9eba6b3c57ce169e
metadata:
  content_kind: web_page
  original_url: https://example.org/article
  truncated: false
```

两者的 `source_id` 相同，因为它们指向同一个归一化 URL。整合时应让成功获取的正文替换摘要，不能把摘要和正文拼接后伪装成一篇正文。抓取失败时可以保留搜索摘要，但必须继续标记为 `search_snippet`。

`fetched_at` 是创建 Source 或获取资料附近的 UTC 时间，不是网页发布时间。

## URL 处理与去重规则

本次采用保守规则：

1. 去掉 URL 字符串两端空白。
2. 从 DuckDuckGo `uddg` 跳转参数中提取真实目标 URL。
3. 只接受带完整主机名的 HTTP(S) URL。
4. 删除 `#fragment`，因为它通常只是同一页面内的定位。
5. 保留 path 的大小写。
6. 保留 query 参数及顺序，不随意解码或重排。
7. 归一化后的同一个 URL 用于去重、生成 `source_id` 和后续抓取。

例如：

```text
https://example.org/article#intro
https://example.org/article#details
```

都会归一化为：

```text
https://example.org/article
```

但下面两个地址不能合并：

```text
https://example.org/list?page=1
https://example.org/list?page=2
```

`parse_qs()` 已经对 `uddg` 做过一次查询参数解码，因此不能再调用一次 `unquote()`。否则目标地址自身的 `%2F` 可能被错误解码为 `/`，改变原始 URL 含义。

## HTML 正文提取规则

`extract_webpage()` 当前使用启发式规则：

- 优先提取 `<main>` 或 `<article>`。
- 找不到时回退到 `<body>`。
- 标题优先取 `<title>`；标题缺失或为空时使用 URL。
- 在提取文本前删除 `script`、`style`、`nav`、`footer` 和 `noscript`。
- 清理空行和每行两端空白。
- 没有正文时抛出 `EmptyContentError`。
- `max_chars` 必须是正整数。
- 正文超过上限时截断，并设置 `metadata.truncated=True`。
- 只有 `<title>` 的页面不能被当成有正文的页面。

这是通用 HTML 启发式，不保证每个网站都能得到干净正文。登录页、验证码页、广告复杂页面和只有 JavaScript 壳的页面仍可能无法正确处理。

## HTTP 请求、错误和重定向

### 搜索链路

- query 先去除首尾空白，空 query 在请求前抛出 `ValueError`。
- `max_results` 只允许 1～10 的整数。
- 明确的“无结果”页面返回空列表。
- HTTP 错误和超时继续作为错误抛出，不能伪装成空结果。
- 验证码页抛出 `SearchServiceError`。
- 无法区分“选择器失效”还是“真的没有结果”时，记录有限预览并报告“不确定”。

### 正文链路

- 只支持 `text/html`，带 `charset=utf-8` 仍属于 HTML。
- JSON、PDF、图片等响应抛出 `UnsupportedContentTypeError`。
- 404 等状态码保留为 `HTTPStatusError`。
- 超时保留为 `httpx.TimeoutException`。
- 当前不自动跟随任意网页的 3xx 跳转，而是抛出 `RedirectUnsupportedError`，避免重定向后绕过第一次地址安全检查。
- HTTP 默认 DNS 端口为 80，HTTPS 默认端口为 443，显式端口保持不变。

## 批量抓取与失败隔离

`collect_pages(candidates, concurrency=3)` 返回：

```python
tuple[list[Source], list[dict]]
```

第一项是成功正文，第二项是结构化失败记录。失败记录包含：

```text
url
source_id
error_kind
status_code
message
```

当前可区分的失败包括：

- `missing_url`
- `unsafe_url`
- `timeout`
- `http_error`
- `redirect_unsupported`
- `unsupported_type`
- `empty_content`
- `network_error`

预期的单页失败只记录当前目标，不应导致整个批次中断。`asyncio.CancelledError` 和程序错误不应被伪装成普通网页失败。

### 固定批次测试

测试输入共 5 个候选：成功页面、404、超时、空正文和一个重复页面。

```text
候选数: 5
唯一 URL/实际抓取数: 4
成功正文数: 1
失败数: 3
失败类别: http_error、timeout、empty_content
concurrency: 3
实测峰值 active: 3
结束后 active: 0
```

这证明了重复候选只抓一次、单个失败不会丢失成功结果，并发峰值不会超过上限。

### offline 演示结果

`day06_web_lab.py --mode offline` 的实际结果：

```text
搜索 fixture 原始有效目标数: 3
归一化去重后 URL 数: 2
批量输入候选数: 3
实际 Mock 抓取数: 2
成功正文数: 1
失败数: 1
失败类别: http_error
模拟状态码: 503
```

该模式只读取 fixture，并用假抓取器模拟网络成功和失败，没有访问互联网。

## 测试设计与 Mock 原则

测试分为三层：

1. 纯解析测试：传入字符串或 fixture，验证字段、清理、URL 和正文规则。
2. HTTP wrapper 测试：使用假 HTTP 客户端返回固定状态、响应头和异常。
3. 批处理测试：使用可控的异步假抓取器验证去重、失败隔离和并发峰值。

正文 HTTP 测试会在单个测试内替换 `ensure_public_url()`，避免发生真实 DNS 查询。地址安全测试则单独替换 `asyncio.get_running_loop().getaddrinfo()`，返回预设的公网或私网 IP。

需要注意：只 Mock `httpx` 不代表完全离线，因为 `ensure_public_url()` 自己还会查询 DNS。测试必须同时控制这一层。

覆盖的核心场景包括：

- 正常搜索、fragment 去重和跳转 URL 编码。
- 缺链接、非法协议、缺摘要和结果数量上限。
- 空搜索、验证码、不确定页面、HTTP 错误和超时。
- 正常正文、非正文标签清理、标题/body 回退和空正文。
- 截断、404、超时、非 HTML 和不跟随重定向。
- 批次混合成功/失败、重复候选和并发限制。
- HTTP(S) 公网允许，本机、私网和混合 DNS 结果拒绝。

## 测试与运行证据

阶段七相关测试命令：

```powershell
E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe -m pytest `
  tests\test_web_search.py `
  tests\test_web_fetch.py `
  tests\test_web_security.py -q
```

最近一次实际结果：

```text
60 passed in 0.37s
```

阶段七完成后还运行过全量测试：

```text
157 passed, 1 warning in 8.67s
```

warning 来自 Starlette 测试客户端依赖中的弃用提示，不是网页功能失败。之后修改 `day06_web_lab.py` 后，又重新运行了网页相关 60 项测试并全部通过。

## 遇到的问题与修复

| 问题 | 原因 | 修复或结论 |
|---|---|---|
| 从 PyCharm 运行时找不到 fixture | 相对路径依赖当前工作目录 | 使用 `Path(__file__).resolve().parents[1]` 定位项目根目录 |
| 两个 fragment 页面没有去重 | 直接使用了带 fragment 的 URL | 使用 `urlsplit/urlunsplit` 删除 fragment 后去重 |
| `%2F` 可能被解码两次 | `parse_qs()` 后又调用 `unquote()` | 删除第二次解码，并用 fixture 固定行为 |
| `max_chars=0` 曾可能通过判断 | 只检查了 `< 0` | 改为必须 `> 0`，并拒绝 bool 和非整数 |
| 只有标题可能被误当正文 | 回退到整个 soup 会包含 head/title | 只回退到 body；没有正文时抛出明确错误 |
| 自动重定向可能绕过 URL 安全检查 | 只在第一次请求前校验地址 | 当前关闭正文自动重定向并明确记录不支持 |
| HTTP 地址被按 443 做 DNS 查询 | 默认端口写死为 443 | HTTP 使用 80，HTTPS 使用 443 |
| Mock HTTP 后仍可能访问 DNS | DNS 查询不经过 httpx | 地址校验单独使用假 getaddrinfo |
| Windows 运行示例出现中文乱码 | 控制台输出编码不一致 | 示例入口将 stdout/stderr 统一配置为 UTF-8 |

## offline 与 live 演示

离线模式：

```powershell
.\.venv\Scripts\python.exe examples\day06_web_lab.py --mode offline
```

- 默认模式。
- 只解析 fixture 并运行 Mock 批次。
- 可以在无网络环境中重复执行。

真实模式：

```powershell
.\.venv\Scripts\python.exe examples\day06_web_lab.py `
  --mode live `
  --query "Python asyncio 官方教程"
```

- 搜索最多 5 条结果。
- 抓取最多 3 个去重目标。
- 并发上限为 3。
- 输出正文长度、前 240 字预览、元数据和失败原因。
- 不循环重试验证码，不关闭 TLS 校验。

## Agent 的接入位置

`workflow.py::_retrieve()` 当前使用以下流程：

```text
SearchProvider.search()
  ↓
取部分搜索候选调用 fetch_webpage()
  ↓
抓取成功：用完整正文替换搜索摘要
抓取失败：保留原搜索摘要
  ↓
merge_ranked()
  ↓
上层整理 Evidence 并生成报告
```

它与本日独立实验的主要区别：

- `workflow.py` 当前只抓取前两个搜索候选。
- 它用 `asyncio.gather(return_exceptions=True)` 隔离失败。
- 它按相同 `source_id` 用完整正文替换搜索摘要。
- 抓取失败时保留摘要，但当前没有把每个失败的详细类别带到最终结果中。
- `collect_pages()` 则明确返回成功列表和结构化失败列表。

网页正文属于外部资料，不属于用户授权或系统指令。网页中即使出现“忽略之前规则”“执行命令”或“读取本地文件”等文字，也只能作为待引用的数据，不能自动执行。

本日只证明了检索链路可以独立运行，没有把网页搜索注册成 MiniAgent 工具，也没有为此调用模型生成报告。

## 真实网络观察

截至本日志记录时，`live` 模式已经实现，但尚未实际运行真实搜索和网页抓取。

因此目前能够确认的是：

- fixture 解析成功。
- Mock HTTP 与 Mock DNS 测试成功。
- 批量并发和失败分类测试成功。
- offline 演示成功。

目前不能声称：

- DuckDuckGo 在当前网络环境中一定可访问。
- 当前选择器与网站最新 HTML 一定一致。
- 任意真实网站都能提取出干净正文。

以后运行 live 模式时应补记：查询词、UTC 时间、搜索服务状态、结果数、成功正文、失败类别，以及人工打开网页核对正文的结果。

## 本次费用

- 模型 API 调用：0 次。
- 付费搜索 API 调用：0 次。
- 外部 API 费用：0 元。
- fixture、Mock 和本地 pytest 不产生 API 费用。

## 当前限制与下一次待补

- [ ] 在网络条件允许时运行一次 `live` 模式并记录真实观察。
- [ ] 人工打开一个成功页面，核对预览关键句确实来自目标网页。
- [ ] 观察真实页面是否混入导航、广告或 Cookie 提示。
- [ ] 评估安全重定向方案：每次跳转重新校验目标地址，而不是永久禁止重定向。
- [ ] 将 `collect_pages()` 的结构化失败信息接入 `workflow.py` 的运行日志。
- [ ] 后续再考虑把搜索能力接入 MiniAgent，以及生成带引用的报告。
- [ ] 检查 `.gitignore` 是否已经忽略 `data/day06/`，避免提交真实抓取输出。
- [ ] 提交前执行 `git diff --check`，并确认没有 API Key、Cookie 或带凭证 URL。

## 复习时应该能够回答

1. 为什么 `search()` 和 `parse_search_html()` 要分开？
2. 为什么 `fetch_webpage()` 和 `extract_webpage()` 要分开？
3. 搜索摘要和网页正文如何通过 `metadata.content_kind` 区分？
4. 为什么 fragment 可以删除，而 query 不能随意删除？
5. 为什么 `parse_qs()` 后不能再次 `unquote()`？
6. 为什么只 Mock httpx 仍可能访问真实 DNS？
7. 为什么任意网页重定向需要重新进行地址安全检查？
8. `collect_pages()` 如何保证一个网页失败不影响其他网页？
9. Semaphore 限制的是并发中的任务数，还是候选总数？
10. `workflow.py` 在正文抓取失败后为什么仍能保留搜索摘要？
11. 为什么网页中的文字不能直接当作 Agent 指令执行？
12. offline 实验能够证明什么，又不能证明什么？
