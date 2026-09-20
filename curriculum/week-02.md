# 第 2 周：搜索、文档与 RAG

本周代码范围：`web.py`、`documents.py`、`retrieval.py`、`citations.py`。

## Day 6：网页搜索

- 核心：阅读 `SearchProvider` 与 `DuckDuckGoHTMLSearch`；用保存的 HTML fixture 测试解析，不让测试依赖真实网络。
- 必须提交：正常、重复 URL、空结果、超时和 HTTP 错误案例。
- 口头检查：搜索摘要和网页正文为什么不能混为一谈？
- 扩展：实现域名白名单。

## Day 7：本地文档

- 核心：加载 TXT、Markdown 和 PDF；检查 chunk 的文件名、页码和 offset；测试扫描型 PDF 提示。
- 必须提交：三类文档统一后的 Source 示例。
- 口头检查：为什么来源元数据必须在切片前建立并在切片后保留？
- 扩展：加入 DOCX Loader。

## Day 8：Embedding 与向量检索

- 核心：先用 `HybridIndex` 理解向量相似度；再安装 vector 扩展并使用 `ChromaIndex` 索引中文资料。
- 必须提交：10 个问题的 Top-3 人工判断表。
- 口头检查：Embedding 存储的是什么？Top-k 高不代表答案正确的原因是什么？
- 扩展：比较两个 Chunk 配置。

## Day 9：混合检索

- 核心：阅读 `merge_ranked()`；分别运行关键词、字符相似度和融合结果；实现来源过滤。
- 必须提交：固定数据集上的三组结果对比。
- 口头检查：关键词检索和语义检索分别擅长什么？
- 扩展：加入轻量重排。

## Day 10：带引用 RAG

- 核心：阅读引用提取、校验和参考资料追加；建立 15 条 RAG 测试；测试伪造 ID。
- 必须提交：一份带网页、文件、PDF 页码引用的报告。
- 口头检查：引用存在为什么仍不代表引用支持该事实？
- 扩展：实现引用支持度人工评分表。

