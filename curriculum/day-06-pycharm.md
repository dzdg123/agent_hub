# Day 06：网页搜索与正文提取——PyCharm 详细学习计划

> 项目：`E:\agent_project\agent-learning-lab`  
> 环境：PyCharm + 项目 `.venv` 中的 Python 3.11  
> 每天总投入：8 小时，各阶段时间灵活分配  
> 今日主线：搜索问题 → 解析结果 → URL 去重 → 获取 HTML → 提取正文 → 保留来源与失败信息

## 1. 今天的目标

第一周完成了模型与工具循环。第二周开始让 Agent 获取外部资料。今天先建立一条可以独立运行和测试的网页检索链路。

例如，输入“Python asyncio 官方教程”，你需要得到一组网页候选，再下载其中几个页面，提取标题、正文、URL 和抓取时间。某个页面超时或返回 404，其他成功页面仍然保留下来。

需要始终区分两种资料：

- **搜索摘要**：搜索服务为结果提供的简短介绍，用于筛选候选。
- **网页正文**：从目标网站实际获取并提取的内容，用于后续证据处理。

搜索摘要里有一句话，不代表程序已读过网页正文。今天让这两种内容都带明确的类型标记，为后面的 RAG 与引用打基础。

今天的核心成果不需要调用 DeepSeek。HTTP 搜索和抓取会访问网络，但不会产生本课的模型 Token 费用。

## 2. 弹性安排与交付物

不规定“阅读两小时、编码三小时”。按检查点推进，遇到不懂的概念先暂停实现，做最小实验后再继续。

| 优先级 | 成果 | 验收依据 |
|---|---|---|
| 核心 | 统一搜索接口 | 输入 query，输出 `list[Source]` |
| 核心 | 可独立测试的搜索解析与正文提取 | 不访问网络即可验证 HTML 处理 |
| 核心 | URL 去重 | 同一 URL 不重复抓取、不重复进入正文结果 |
| 核心 | 批量正文获取 | 限制并发，保留成功项和明确失败项 |
| 核心 | 离线 HTML fixtures 与 Mock HTTP 测试 | 正常、空结果、超时、404、空正文都可重现 |
| 核心 | 一次真实网络观察 | 保存结果；网络不可用时明确记待补 |
| 核心 | 学习日志与 Git 提交 | 能解释完整请求和来源处理链路 |
| 扩展 | 域名过滤、发布时间、连接复用 | 核心链路完成后再做 |

如果 8 小时结束仍有核心项未完成，写入待补列表，下次先补齐。今天不要求生成研究报告，也不要求开发完整爬虫。

## 3. 当前项目起点

2026-10-04 阅读代码时，已有以下能力：

- `web.py` 定义了 `SearchProvider` 抽象接口。
- `DuckDuckGoHTMLSearch` 使用无密钥 HTML 搜索入口，解析 `.result`、`.result__a` 和 `.result__snippet`。
- `fetch_webpage()` 使用 httpx 获取网页，BeautifulSoup 清理标签并提取正文。
- `ensure_public_url()` 检查协议、账号信息、本机及解析到的非公网地址。
- `Source` 已有 source_id、title、content、url、fetched_at 和 metadata。
- `tests/test_web_security.py` 已有协议与本机 URL 拒绝案例。
- Day 05 的 `MiniAgentStatus` 与 `MiniAgentResult` 已出现在 models.py 中。

今天重点补齐的是解析测试、失败分类和批量处理。当前搜索与正文解析混在网络方法中，可以先提取纯函数，提高可测试性。

HTML 搜索入口及页面选择器可能随网站调整；有接口实现不等于服务永远可用。不要把一次抓取失败理解为需要重装 Python。

## 4. 操作哪些文件

路径相对于项目根目录。以下新增函数与文件是今天的练习建议，不代表项目已经提供。

| 文件 | 操作 | 重点 |
|---|---|---|
| `src/research_agent/web.py` | 核心修改 | 搜索接口、纯解析函数、URL 处理、网络错误 |
| `src/research_agent/models.py` | 阅读为主 | 复用 Source，不随意改公共类型 |
| `src/research_agent/documents.py` | 阅读 content_id | 理解稳定来源编号如何生成 |
| `src/research_agent/workflow.py` | 只读对照 | 查看搜索摘要与抓取正文如何进入工作流 |
| `tests/fixtures/day06/search_results.html` | 新建 | 合成搜索页，包含正常、重复和异常链接 |
| `tests/fixtures/day06/article.html` | 新建 | 合成文章，含正文及应被清理的内容 |
| `tests/fixtures/day06/empty.html` | 新建 | 无可用正文 |
| `tests/test_web_search.py` | 新建 | 搜索结果解析与 HTTP 错误 |
| `tests/test_web_fetch.py` | 新建 | 正文提取、抓取错误、批量失败隔离 |
| `tests/test_web_security.py` | 补充 | URL 校验保持有效，不访问真实 DNS |
| `examples/day06_web_lab.py` | 新建 | 离线与真实网络两个实验入口 |
| `curriculum/day-06-log.md` | 新建 | 来源样例、测试、网络观察和复盘 |
| `.gitignore` | 按需追加 | 忽略当天的运行输出目录 |

fixtures 是你手写的合成小 HTML，应该进入 Git。真实抓取输出与调试缓存放在 `data/day06/` 并忽略，不把它们误当成 fixtures。

## 5. 开始前检查

### 5.1 确认环境

在 PyCharm Terminal 执行：

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import httpx, bs4; print('httpx:', httpx.__version__); print('bs4:', bs4.__version__)"
.\.venv\Scripts\python.exe -m pytest tests/test_web_security.py -q
```

这些依赖已列在 pyproject.toml。导入成功就继续，不需要为了今天升级所有依赖。

### 5.2 前置自查

- [ ] 能解释 HTTP 请求、响应、状态码和响应头。
- [ ] 能解释 HTML 与 JSON 的区别。
- [ ] 能说明 await 为什么适合网络等待。
- [ ] 会使用 gather 与 Semaphore 保留多个任务结果。
- [ ] 知道 Mock HTTP 与真实网络实验分别证明什么。

Day 05 若还有失败测试，先把影响工具或模型基础功能的核心问题记清楚；网页纯解析实验可以独立进行，不必等所有扩展任务完成。

## 6. 阶段一：画清网页链路并阅读接口

打开 web.py，按以下顺序阅读：

```text
SearchProvider
→ DuckDuckGoHTMLSearch.search()
→ ensure_public_url()
→ fetch_webpage()
```

写出流程：

```text
query
  → SearchProvider.search()
  → 搜索服务 HTML
  → 标题、目标 URL、摘要
  → URL 去重
  → 每个目标页面 HTTP 请求
  → HTML 清理与正文提取
  → Source 列表 + 抓取失败记录
```

### 阅读时回答

1. 为什么要有 SearchProvider，而不是把某个搜索网址写进 Agent？
2. `params={"q": query}` 把关键词放到请求的哪个位置？
3. `.result__a` 是什么？它为什么可能失效？
4. search 返回的 content 当前来自哪里？
5. fetch_webpage 返回的 content 当前来自哪里？
6. Source 的 source_id 与 URL 有什么关系？

`content_id(url)` 对输入字符串计算哈希，前缀 web- 表明来源类别；它没有证明网页可信，也没有识别网页内容是否更新。

**检查点：**能指出摘要和正文在代码中各自的生产位置，能说明统一接口对替换搜索来源有什么帮助。

## 7. 阶段二：先用本地 HTML 学会提取

### 7.1 手写文章 fixture

在 PyCharm 中创建 `tests/fixtures/day06/article.html`，输入：

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>异步学习笔记</title>
  <style>body { color: black; }</style>
</head>
<body>
  <nav>首页 登录 广告入口</nav>
  <main>
    <article>
      <h1>异步请求</h1>
      <p>网络请求主要花时间等待远程响应。</p>
      <p>多个独立请求可以并发推进。</p>
      <script>console.log('不应进入正文');</script>
    </article>
  </main>
  <footer>页脚测试文字</footer>
</body>
</html>
```

这是本课的合成资料，不是某篇真实文章。

### 7.2 观察 BeautifulSoup

在 day06_web_lab.py 中先运行这个本地实验：

```python
from pathlib import Path

from bs4 import BeautifulSoup

html = Path("tests/fixtures/day06/article.html").read_text(encoding="utf-8")
soup = BeautifulSoup(html, "html.parser")
print("标题:", soup.title.get_text(" ", strip=True))

for element in soup(["script", "style", "nav", "footer", "noscript"]):
    element.decompose()

main = soup.select_one("main, article") or soup.body or soup
print("正文:", main.get_text("\n", strip=True))
```

运行后判断：

- 标题是否为“异步学习笔记”？
- 是否保留两段正文？
- 是否去掉脚本、样式、导航和页脚？
- `get_text()` 的分隔符怎样影响输出？

参见 [BeautifulSoup 官方文档](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)。

### 7.3 提取纯函数

将 fetch_webpage 中的 HTML 解析逻辑移到建议的新函数：

```python
def extract_webpage(
    html: str,
    url: str,
    max_chars: int = 30000,
) -> Source:
    ...
```

省略号由你实现。这个函数只处理传入的字符串，不发网络请求、不查询 DNS。

约定：

- 优先提取 main/article，再回退到 body。
- 没有 title 或标题为空时，用 URL 作标题。
- 去掉明确的非正文标签，整理空白行。
- 没有可用正文时抛出清楚的解析错误。
- max_chars 必须为正整数，正文超出时截断并标记 metadata.truncated。
- 对无 main/article 的回退页面，避免把 head/title 当成正文；只有标题的页面仍应识别为空正文。

提取器只是 HTML 启发式，不保证每个网站都得到干净正文。验证码、登录页与只有 JavaScript 壳的页面需要单独识别或记录局限。

**检查点：**纯函数测试无需网络，能从自己的 fixture 得到可预测内容。

## 8. 阶段三：解析搜索结果和 URL 去重

### 8.1 手写搜索 fixture

创建 `tests/fixtures/day06/search_results.html`：

```html
<html><body>
  <div class="result">
    <a class="result__a" href="https://example.org/article#intro">异步教程</a>
    <div class="result__snippet">关于协程与等待的摘要。</div>
  </div>
  <div class="result">
    <a class="result__a" href="https://example.org/article#details">重复页面</a>
    <div class="result__snippet">同一网页的另一个定位片段。</div>
  </div>
  <div class="result">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fother">另一篇文章</a>
  </div>
  <div class="result">
    <a class="result__a" href="javascript:alert(1)">无效链接</a>
  </div>
  <div class="result">
    <div class="result__snippet">缺少链接的条目。</div>
  </div>
</body></html>
```

### 8.2 提取解析函数

建议新增：

```python
def parse_search_html(html: str, max_results: int = 5) -> list[Source]:
    ...
```

让 search() 负责 HTTP 请求，成功后调用 parse_search_html。保留 SearchProvider 原有 async search 签名，避免破坏使用它的代码。

### 8.3 URL 的处理规则

今天先实现保守去重：

1. 去掉字符串两端空白。
2. 从搜索跳转链接提取真正目标 URL。
3. 只接受完整 HTTP(S) 目标，其他条目跳过。
4. 去掉 `#fragment`，因为它通常只是同一页面的定位位置。
5. 保留 path 的大小写和 query 参数，不随意解码或重排。
6. 使用处理后的同一 URL 字符串进行去重、生成 source_id 和后续抓取。

可通过 urllib.parse 的 urlsplit/urlunsplit 去掉 fragment。把这段处理放到统一 helper，别让搜索和批量抓取各写一套规则。

**不要为了提高去重率就删除所有 query。** `?page=1` 与 `?page=2` 可能是两份不同内容。

当前代码对 uddg 用 parse_qs 后又 unquote。parse_qs 已做了一层查询参数解码；再次 unquote 可能改变目标 URL 自身的百分号编码。增加一个目标 query 含 `%2F` 的 fixture，确认不要重复解码。

### 8.4 输入与空结果契约

- 先对 query 去掉首尾空白；空 query 在发送请求前抛 ValueError。
- 本教学项目将 max_results 限为 1～10，超出抛 ValueError；这是项目约定，不是网站标准。
- 成功响应中明确没有结果，返回空列表。
- HTTP 错误、超时、明显验证码页，作为服务失败说明，不悄悄伪装为“没有相关资料”。
- 选择器失效与真正无结果有时无法仅凭 HTML 准确区分。保留诊断信息和有限预览，日志说明“不确定”，不要编造结果。

**检查点：**fixture 最终应得到两条不同目标；第一条的两个 fragment 只保留一次，缺摘要的条目允许 content 为空字符串。

## 9. 阶段四：为来源加上明确的元数据

复用 Source，在 metadata 中定义本课约定：

| 字段 | 搜索结果 | 正文结果 |
|---|---|---|
| content_kind | `search_snippet` | `web_page` |
| provider | `duckduckgo_html` | 可保留搜索来源或省略 |
| original_url | 搜索解析得到的原始目标 | 原始请求目标 |
| truncated | 一般 False | 正文是否因 max_chars 截断 |

fetched_at 保留为对象构建/资料获取附近的 UTC 时间；它不是网页发布时间。纯 fixture 实验中的值是解析样例的时间，应在日志注明。

同一个归一化 URL 的搜索条目和正文应该使用一致 source_id。整合时正文替换摘要，不把两种 content 相加后伪装成一篇正文。

在日志保存一条搜索 Source 和它对应的正文 Source，指出标题、content、metadata 的变化。不能把搜索失败时返回的错误文字塞入正文 content。

**检查点：**以后交给模型的资料能明确表明是摘要还是已获取正文，引用可以追溯到目标 URL。

## 10. 阶段五：HTTP 获取、错误与重定向

### 10.1 阅读现有请求

在 fetch_webpage 中找到：

```text
ensure_public_url
→ AsyncClient
→ client.get
→ response.raise_for_status
→ content-type 检查
→ response.text
→ extract_webpage
```

看懂 Content-Type 为什么影响解析。今天正文链路支持 text/html，包含 `; charset=utf-8` 仍是 HTML；PDF 或 JSON 响应明确返回“不支持的类型”。PDF 文档解析将在后续本地文档课程处理。

状态码和响应处理参见 [HTTPX QuickStart](https://www.python-httpx.org/quickstart/)。

### 10.2 明确不同错误

| 类别 | 场景 | 单个抓取的行为 |
|---|---|---|
| 参数错误 | 空 URL、无效 timeout/max_chars | 请求前拒绝 |
| URL 拒绝 | file://、本机、非公网目标 | 记录 unsafe_url，不发送 HTTP |
| 超时 | 网络读取一直等待 | 记录 timeout |
| HTTP 错误 | 404、403、500 | 保存状态码，不能提取错误页冒充正文 |
| 不支持类型 | PDF/JSON/图片 | 记录 unsupported_type |
| 空正文 | 只有空白或被清理的标签 | 记录 empty_content |
| 服务拦截 | 登录页、验证码 | 明确不可用或需人工判断 |

可以在 web.py 定义几个清晰的 ValueError 子类表示解析问题；HTTP 异常也可以保留 httpx 原类型，交给批处理分类。不要为今天引入复杂异常框架。

HTTPX 的 timeout 通常约束连接、读、写与连接池等待，并不自动等于整个抓取流程的墙钟上限。若需要包括 DNS 检查在内的总时间预算，额外用 asyncio.wait_for 包裹整次抓取；参见 [HTTPX 超时说明](https://www.python-httpx.org/advanced/timeouts/)。

今天默认不重试，先得到明确结果；有限重试作为扩展，不能用无限重试掩盖 403 或 404。

### 10.3 处理当前重定向边界

现有 fetch_webpage 在校验初始 URL 后使用 follow_redirects=True，重定向后的每个目标并没有重新经过本地校验。

本课选择简单策略：**抓取任意候选网页时关闭自动跟随重定向**，对 3xx 记录 `redirect_unsupported`。真实站点若有跳转，记录失败原因，暂不把跳转后的地址当成成功正文。

这是本课的抓取行为约定；搜索服务本身固定入口的重定向处理单独阅读，不要混为同一类任意 URL 获取。

如果想支持重定向，放到扩展：手动解析 Location、用 urljoin 得到绝对 URL，每次请求前校验，设置最多跳转次数。仅在自动跳转结束后校验最终地址，无法阻止中途请求已发生。

当前 ensure_public_url 属于基础检查，DNS 检查与实际连接仍可能是两次解析，不宣称它已解决所有地址变化问题。今天保留检查、修复明显的自动跳转绕过即可。

**检查点：**HTTP 200 不保证正文可用；请求错误与解析错误分别能定位。

## 11. 阶段六：批量抓取，保留成功与失败

在 web.py 中新增一个小的批处理 helper，例如：

```python
async def collect_pages(
    candidates: list[Source],
    concurrency: int = 3,
) -> tuple[list[Source], list[dict]]:
    ...
```

返回第一项是正文列表，第二项是失败记录。它不改变 SearchProvider 或现有 fetch_webpage 的返回类型。

### 11.1 建议实施顺序

1. 验证 concurrency 为正整数。
2. 对候选 URL 统一处理并去重，没有 URL 的候选单独记录，不发请求。
3. 每个独立 URL 创建一个工作协程，共享 Semaphore。
4. 取得名额后抓取，使用明确的请求超时和可选总时间预算。
5. 对预期网络/内容错误返回结构化失败项。
6. 收集全部结果，不因一个超时中断其他页面。
7. 正文输出再次按归一化 URL/source_id 去重。

失败项建议：

```json
{
  "url": "https://example.org/missing",
  "source_id": "web-example-id",
  "error_kind": "http_error",
  "status_code": 404,
  "message": "网页不存在"
}
```

示例编号用于说明结构，实际编号仍由程序生成。日志不要把原始凭证、Cookie 或整个响应头拼进去。

### 11.2 失败隔离的实现选择

可以在每个 worker 中捕获预期的 httpx 网络异常、URL 拒绝、你定义的网页内容异常和总超时，转换为失败记录，再用 gather 汇总。

不要把所有开发异常都变成“网页抓取失败”。如果使用 `gather(return_exceptions=True)`，应区分预期错误与意外异常；拼写错误、断言错误需要在开发时暴露。取消继续传播。

### 11.3 固定批次实验

Mock 一组候选：成功页面、404 页面、超时页面、空正文页面，再加入一个成功页面的重复 URL。

预期：

```text
候选 5 条
去重后 4 个目标
成功正文 1 条
失败记录 3 条
重复页面没有第二次 HTTP 请求
```

通过 Mock 路由 call_count 证明没有重复请求，不只看最终列表长度。

加运行计数器，记录 active/peak_active，在 finally 中减少 active。确认峰值不超过 3，全部结束后 active=0；出现失败仍能释放并发名额。

### 11.4 是否保留失败网页的搜索摘要

正文获取失败时，原搜索摘要可以作为单独的候选资料保留，但必须仍标记 content_kind=search_snippet、fetch_error=具体原因。核心正文结果列表只放成功正文，失败摘要不得冒充已抓取证据。

当前 workflow.py 的 _retrieve() 使用 `full_pages or search_results`，正文全部失败时会退回摘要。今天只阅读并指出这一策略；元数据让后续课程能够识别回退，不要求今天重写研究工作流。

**检查点：**知道哪些来源获得了正文，哪些只保留摘要，以及每次失败的原因。

## 12. 阶段七：测试不依赖互联网

创建 tests/test_web_search.py 与 tests/test_web_fetch.py，继续复用项目已安装的 pytest、respx 和 httpx。

### 12.1 分三层测试

| 层 | 输入 | 是否 Mock 网络 | 证明什么 |
|---|---|---|---|
| 纯解析 | 手写 HTML 字符串/fixture | 无网络可 Mock | 字段、清理、URL 去重和正文规则 |
| HTTP wrapper | 预设 HTTP 响应 | respx | 状态码、超时、类型、解析连接起来 |
| 批处理 | 一组候选及响应 | respx/可控异步假抓取器 | 一个失败不丢失其他结果，限制并发 |

fixture 读取建议使用基于测试文件的路径，而不是依赖 Terminal 的当前目录：

```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "day06"
html = (FIXTURES / "article.html").read_text(encoding="utf-8")
```

### 12.2 核心测试清单

按行为写测试，可对相关输入使用参数化，不需要强行写成一个巨大测试函数。

| ID | 场景 | 核心断言 |
|---|---|---|
| S01 | 正常搜索 HTML | 标题、目标 URL、摘要正确，类型为 search_snippet |
| S02 | 重复 URL 与 fragment 变体 | 只保留一个页面，source_id 一致 |
| S03 | 跳转 URL 编码 | uddg 正确解码，目标 query 中编码不被多解一层 |
| S04 | 缺链接、非法协议、缺摘要 | 前两类跳过，缺摘要保留为空字符串 |
| S05 | 空搜索结果与 max_results | 空页得到空列表，数量不超限；非法输入请求数为 0 |
| S06 | 搜索服务超时/HTTP 错误 | 明确抛出或包装失败，不直接返回假空结果 |
| F01 | 正常正文 fixture | 标题、正文、URL、来源编号保留，类型为 web_page |
| F02 | HTML 清理 | script/style/nav/footer 内容不进入正文 |
| F03 | 缺 title/无 article | 回退标题与 body 行为符合约定 |
| F04 | 空正文、只有 title | 明确 empty_content |
| F05 | max_chars 截断与非法上限 | 长度受限，truncated 正确；非法输入及时拒绝 |
| F06 | 404、超时、非 HTML | 三类原因分别可定位 |
| F07 | 3xx 重定向 | 不自动请求跳转目标，记录不支持重定向 |
| B01 | 混合成功/失败批次 | 成功保留，错误不混入正文 |
| B02 | 重复候选 | Mock 路由只被抓取一次 |
| B03 | 并发限制 | 峰值不超上限，失败后 active 为 0 |
| U01 | 地址校验 | HTTP(S) 与公网检查保留；本机和私网拒绝 |

### 12.3 Mock HTTP 也要处理 DNS

respx 拦截 httpx 请求，但不会自动拦截你自己调用的 loop.getaddrinfo。因此直接 Mock fetch_webpage 仍可能发生真实 DNS 查询。

针对 HTTP wrapper 测试，可以仅在该测试内替换地址校验：

```python
async def fake_public_url(url):
    return url

monkeypatch.setattr("research_agent.web.ensure_public_url", fake_public_url)
```

这是测试隔离，不是生产代码修改。然后 respx 对所有预期请求返回固定响应，并保持未匹配请求报错，不能使用 pass-through。

原地址校验另写独立测试，用 monkeypatch 替换事件循环的 getaddrinfo，返回预设 IP。分别覆盖公网、私网和同域名同时解析出两类地址的情况；混合结果应拒绝。

这样可以同时证明正文 wrapper 行为与地址校验行为，又不依赖真实 DNS。不要在整个测试套件里全局永久替换校验函数。

Mock 路由、异常与调用次数可参考 [RESPX 官方说明](https://lundberg.github.io/respx/guide/)。

### 12.4 超时测试要确定可重复

单个 HTTP 超时通过 Mock 直接抛 `httpx.ReadTimeout`；不要访问故意很慢的公共网站。

批次并发测试可以用本地 await/Event 模拟等待，并测峰值。不要断言耗时必须正好等于某个毫秒数。

**检查点：**断网情况下，核心测试仍能通过；空结果、网络错误和内容错误有不同证据。

## 13. 阶段八：在 PyCharm 中运行离线与真实演示

### 13.1 建立入口

完善 examples/day06_web_lab.py，让脚本有明确模式，例如：

```text
offline：解析 fixtures，运行 Mock 批次，显示正常与失败结果
live：访问一次真实搜索服务，抓取至多 3 个去重目标
```

模式是你在脚本中通过 argparse 实现的参数，不是已有项目 CLI 命令。

建议参数：

```text
--mode offline
--mode live --query "Python asyncio 官方教程"
```

offline 默认运行，不应在导入模块时发请求。保留 `if __name__ == "__main__"` 入口。

### 13.2 PyCharm 配置

| 配置项 | 内容 |
|---|---|
| 名称 | `Day06 Web Lab Offline` |
| 类型 | Python，脚本路径 |
| 脚本路径 | `E:\agent_project\agent-learning-lab\examples\day06_web_lab.py` |
| 参数 | `--mode offline` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | `E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe` |

复制配置为 `Day06 Web Lab Live`，参数换成：

```text
--mode live --query "Python asyncio 官方教程"
```

### 13.3 真实运行观察什么

只执行少量请求，例如搜索候选最多 5 条、正文抓取最多 3 条、并发上限 3。避免把调试变成反复请求同一网站。

记录：

- 查询词与运行时间。
- 搜索服务响应状态、结果数。
- 原始目标与去重后的 URL 数量。
- 成功正文数量、每个标题与正文长度。
- 失败目标、状态码或错误类别。
- 正文前 200～300 字的人工质量判断。
- 来源 URL、source_id、content_kind、fetched_at。

打开一个成功页面人工对照：正文中的关键句是否真的出现在网页中，导航广告是否仍混入。需要网页登录、验证码或 JavaScript 渲染的页面，明确记录为当前方法的局限。

### 13.4 搜索服务不可用时如何继续

按顺序定位：

1. 状态码与异常类型是什么？
2. 返回 HTML 是搜索页、验证码还是错误页面？
3. 当前选择器还能匹配吗？
4. HTTP 请求是否受到本地代理、网络或网站拦截影响？

不要循环重试验证码，不关闭 TLS 校验，不把无响应写成“无相关资料”。

可以单独用 fetch_webpage 尝试一个公开官方文档页面，例如 Python asyncio 文档，验证“已知 URL → 正文”链路；这不等于搜索服务已经接通。

保留 fixture/Mock 的全部核心证据，将真实搜索观察写成待补。若以后更换来源，只需增加 SearchProvider 实现并保持接口一致；今天无需临时引入新的付费 API。

**检查点：**能准确说明哪些环节真实访问成功，哪些仅在合成资料上验证。

## 14. 阶段九：对照 Agent 的接入位置

打开 workflow.py 的 _retrieve()，只做阅读：

```text
SearchProvider.search()
→ fetch_webpage()
→ 成功网页或摘要回退
→ merge_ranked()
→ 上层整理证据
```

在日志写出与你今天链路的差别：它目前只抓部分候选，并以完整正文是否存在决定回退；今天的演示明确保留每个失败原因和资料类型。

网页文字是外部资料。以后把它交给模型时，应作为可引用的数据处理；页面里要求“忽略规则”“执行某个命令”的文字，不自动成为用户授权或程序执行指令。

本课先证明检索链路可独立运行；把搜索工具加入 MiniAgent 或生成带引用报告留到后续整合，不让模型费用干扰今天的解析调试。

## 15. 回归与诊断

先在 PyCharm 右键运行单个新测试，通过后执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web_search.py tests/test_web_fetch.py tests/test_web_security.py -q
```

由于修改了共用 web.py，再运行依赖该模块的现有测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_web_search.py tests/test_web_fetch.py tests/test_web_security.py tests/test_workflow.py tests/test_mcp_server.py -q
```

根据实际修改再决定是否运行整个套件。保存实际结果，不把计划中的通过数当作执行结果。

| 现象 | 先检查 |
|---|---|
| 返回空列表 | HTTP 内容、是否验证码、选择器、max_results |
| 中文乱码 |响应编码与 fixture 是否用 UTF-8；不要随意删除中文 |
| 重复页面 | 跳转链接是否正确解包、fragment 是否去掉、请求前是否去重 |
| 正文里有脚本和导航 | 清理发生在 get_text 前还是后 |
| 只有标题也被当正文 | 回退范围是否包含 head/title |
| 所有 Mock 测试仍查询网络 | 是否漏掉自定义 DNS 查询或用了 pass-through |
| 一个 404 导致全部中断 | worker 的预期异常边界与 gather 策略 |
| 抓取超时仍卡住 | 是否包括地址检查/排队，是否有阻塞代码 |
| 来源 ID 不一致 | 搜索与抓取是否使用同一种归一化 URL |

如果完整回归出现系统临时目录权限错误，先确认报错路径，沿用前几天的专用 pytest 临时目录方法，不改正文提取逻辑去“修复”权限。

## 16. 学习日志与 Git 提交

新建 curriculum/day-06-log.md，至少包含：

```markdown
# Day 06 学习日志

## 完整链路与文件职责

## 搜索摘要与网页正文的区别
保存一组 Source 对照样例。

## URL 去重规则
处理了什么，明确保留了什么。

## 固定批次实验
候选数、唯一 URL 数、成功数、失败类别、峰值并发。

## HTML 解析与 Mock 测试
测试命令、实际结果、至少一个失败及修复。

## 真实网络观察
查询、运行时间、成功目标与失败原因；不可用则写待补。

## 本次费用
模型调用 0 次；如自行增加外部付费搜索服务，单独记账。

## 当前限制与下一次待补
```

将 data/day06/ 加入 .gitignore。fixtures 与测试属于代码资产，运行抓取输出属于本地实验数据。

在项目根目录检查：

```powershell
git status
git diff --check
```

按实际新增和修改文件暂存，不存在的路径从命令中去掉：

```powershell
git add src/research_agent/web.py tests/test_web_search.py tests/test_web_fetch.py tests/test_web_security.py tests/fixtures/day06 examples/day06_web_lab.py curriculum/day-06-pycharm.md curriculum/day-06-log.md .gitignore
git diff --cached --stat
git status
git commit -m "learn: add web search extraction and failure handling"
```

检查暂存内容中没有 API Key、Cookie、带凭证 URL 或敏感抓取资料。没有 Git 仓库时，先确认根目录并初始化，再补可复现的基础文件提交。

## 17. 有余力再做的扩展任务

1. **域名过滤：**允许 example.org 及明确选择的子域名规则。通过 hostname 比较，不能用字符串包含判断，否则 example.org.attacker.test 可能误匹配。
2. **手动重定向：**每一跳先校验目标，并设最多 3 次跳转；记录原始 URL 与最终 URL。
3. **连接复用：**为抓取函数增加可选 AsyncClient 参数，批次共享一个 client；明确由创建者负责关闭。参见 [HTTPX 异步客户端说明](https://www.python-httpx.org/async/)。
4. **发布时间：**从 meta/time 元素提取，失败时保留 None，区分 published_at 与 fetched_at，不猜时间。
5. **字节大小限制：**当前 max_chars 只限制解析后的正文字符数，不限制下载体大小；用流式读取和累计字节设置边界。
6. **有限重试：**只针对临时网络错误/部分服务端错误，设置最大次数；403、404、空正文不盲目重试。
7. **内容更新：**讨论同一个 URL 的内容发生变化时，为什么 URL 哈希不能作为内容版本号。

## 18. 今日最终验收清单

- [ ] 能解释 SearchProvider、具体搜索适配器、正文获取器各自的职责。
- [ ] query 与 max_results 合法性在请求前检查。
- [ ] 搜索解析与正文提取可用本地 HTML 单独验证。
- [ ] 搜索结果有标题、目标 URL、摘要及稳定来源编号。
- [ ] 重复 URL 在请求前去重，不重复进入最终正文列表。
- [ ] 正文去掉 fixture 中的脚本、样式、导航和页脚。
- [ ] 搜索摘要和抓取正文通过 content_kind 明确区分。
- [ ] 404、超时、非 HTML、空正文分别有清楚结果。
- [ ] 一项失败不影响其他成功项，名额与连接正常释放。
- [ ] 公网 URL 检查保留，自动重定向策略明确。
- [ ] 核心测试不依赖真实 HTTP 或 DNS。
- [ ] 完成少量真实网络观察，或准确记录待补原因。
- [ ] 日志、测试证据与 Git 提交齐全。

本课不要求“真实搜索每次都成功”，但需要能判断服务不可用、解析失败和真实空结果，并有稳定的离线验证证据。

## 19. 不看笔记的口头验收题

1. 搜索摘要与网页正文分别从哪里获取？
2. BeautifulSoup 做了什么，为什么它不会执行 JavaScript 来加载正文？
3. HTTP 200 为什么仍可能不是有效文章？
4. 为什么有 max_chars 不代表限制了下载文件大小？
5. 为什么不能删除所有 URL 查询参数来去重？
6. 去重应该放在抓取前还是抓取后？两者各解决什么？
7. 没有结果与搜索服务超时应如何区分？
8. 为什么 Mock HTTP 后还可能查询 DNS？
9. 一个页面失败时，怎样证明其他页面成功结果没有丢失？
10. fetched_at 为什么不能当作网页发布时间？
11. URL 哈希是否能证明来源可信或内容没变？
12. 页面里的“忽略之前规则”为什么不能当作用户新指令？

## 20. 按需查阅的官方资料

- [HTTPX QuickStart](https://www.python-httpx.org/quickstart/)：请求、参数、响应和状态码。
- [HTTPX Timeouts](https://www.python-httpx.org/advanced/timeouts/)：不同等待阶段的超时。
- [HTTPX Async Support](https://www.python-httpx.org/async/)：异步请求和连接生命周期。
- [BeautifulSoup 文档](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)：选择元素、清理标签、提取文本。
- [RESPX Guide](https://lundberg.github.io/respx/guide/)：Mock 响应、异常和调用次数。

Day 07 将处理 TXT、Markdown 和 PDF 本地文档。网页与本地资料将统一进入 Source，随后再学习切片、Embedding、混合检索和带引用的回答。
