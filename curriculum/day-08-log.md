# Day 08 学习日志：Embedding、Chroma 与可验证的向量检索

学习与实验跨度：2026-10-14～2026-10-19。日志整理日期：2026-10-19。

这份日志按课程阶段整理，不表示全部工作在同一天完成。代码和语料由 Codex 协助实现，我在 PyCharm 中运行实验并逐步理解接口、输出和原理；候选证据评分也由 Codex 辅助逐条审核，不是独立人类评审。

## 先回忆：这次到底做成了什么

Day 07 解决“把原始文件变成可追溯的 Source”。Day 08 接着解决“把 Source 变成向量并保存，用问题找到候选证据，验证结果是否支持问题”。

现在已经打通：

```text
原始 TXT / Markdown / 文本型 PDF
  → Day 07 loader：规范化、字符切片、保留页码和 offset
  → Source[]
  → embed_documents(contents)：检查 token 长度、模型编码、L2 归一化
  → Chroma upsert：保存 ID、正文、向量、来源信息

用户问题
  → embed_query(query)：同一模型、固定预处理、长度检查、L2 归一化
  → Chroma query(query_embeddings)：按 cosine distance 找近邻
  → 最多 Top-k 条候选
  → 对齐返回数组，恢复 Source[]
  → 逐条判断正文是否支持问题，计算 Hit@3
```

本课的交付是检索层和检索评测。没有接入聊天模型生成最终研究回答；runtime 的默认索引仍是 HybridIndex。

主要结果：

| 验证 | 实际结果 | 证明的范围 |
| --- | --- | --- |
| 真实 BGE 编码 | 输出 512 维；文档和查询均启用 L2 归一化 | 模型及编码链路可用 |
| 固定语料准备 | 12 份原始资料，生成 13 个 Source | 文件经真实加载器进入评测 |
| 固定语料长度 | 最长片段 177 tokens，最长问题 25 tokens，上限 512，超长数均为 0 | 当前输入没有超模型长度 |
| 持久化实验 | 首次写入 4，重复写入仍为 4，删除后为 3，新进程打开仍为 3 | upsert 幂等、精确删除和磁盘持久化 |
| Top-3 预标注核对 | 正向题 10/10 找到预标注证据 ID | 自动 ID 匹配通过 |
| 内容审核 | 36 条候选全部评分；正向 Top-1 为 9/10，Hit@3 为 10/10 | 按本次 AI 辅助内容审核，达到至少 8/10 的教学目标 |
| 阶段九相关回归 | 115 passed；pip check 无依赖冲突 | 指定数学、模型边界、存储和文档测试通过 |

这几项是不同实验：最初 Day 07 样例有 4 个 Source，固定评测语料有 13 个 Source，不能混用计数。115 是最后一次指定相关测试文件的总数，不是声称最新整个仓库只有这些测试。

## 阶段一：理解频次向量和余弦

阅读 `src/research_agent/retrieval.py` 的 `tokenize()`、`_cosine()` 和 `HybridIndex.search()`。

`Counter` 是计数容器，用词项或字符作键、出现次数作值，可以理解成稀疏的频次向量。比较两段文本时，同一个键对应同一个维度，缺失项按 0 处理。

当前 tokenize 并非中文语义分词模型：英文等用正则提取，中文主要采用相邻双字符片段。字符分支则直接统计小写文本中的字符，包括可能出现的空白和标点。

HybridIndex 的分数是：

```python
score = 0.7 * keyword_score + 0.3 * char_score
```

0.7 和 0.3 是代码中人工设定的权重，没有训练过程。它混合的是两种频次相似度，不能因名字中有 Hybrid 就认为已经融合了神经向量检索。

学习到的边界：

- 频次检索依赖表面重合，难以可靠识别同义表达。“汽车”和“轿车”共享“车”字，但词项不同；即使字符分支给出一点分数，也不等于理解同义关系。完全没有重合时更容易漏检。
- “可以公开密钥”和“不可以公开密钥”共享大量文字，却事实相反，频次余弦仍可能较高。
- 余弦是比较向量方向的方式，Embedding 是生成表示的方式，两者不是同一个概念。

余弦公式与实验：

```text
cos(a, b) = dot(a, b) / (norm(a) × norm(b))

[1, 0] 与 [1, 0]   →  1
[1, 0] 与 [0, 1]   →  0
[1, 0] 与 [-1, 0]  → -1
[1, 0] 与 [10, 0]  →  1
```

缩放长度不改变方向。零向量没有方向，严格的数学实验应拒绝零向量、空向量、维度不一致和非有限数。
本次将独立数学函数提取到 `src/research_agent/vector_math.py`，实验脚本和数学测试共用它；HybridIndex 的内部频次 `_cosine()` 保留空计数返回 0 的原有行为。

## 阶段二：建立统一的 Embedding 层

新增 `src/research_agent/embeddings.py`：

```python
class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
```

真实实现是 `SentenceTransformerEmbedder`。构造时加载一个 SentenceTransformer，后续反复复用，而不是每次查询都加载模型。
ChromaIndex 依赖这个协议，可以注入真实模型，也可以注入返回固定小向量的 FakeEmbedder。

本次固定基线配置：

| 项目 | 实际设置 |
| --- | --- |
| 模型 | BAAI/bge-small-zh-v1.5 |
| 实际模型快照 | 7999e1d3359715c523056ef9478215996d62a620 |
| 设备 | CPU |
| 实测输出维度 | 512 |
| model.max_seq_length | 512 tokens |
| 文档输入 | 直接编码正文 |
| 查询输入 | 直接编码原问题，不加查询指令 |
| 两端归一化 | normalize_embeddings=True，即 L2 归一化 |
| 输出格式 | Python float 列表 |

数值上同样是 512，但“512 tokens 输入上限”和“512 维输出向量”是两个独立概念，只是此模型恰好取值相同。

编码层还检查空字符串、维度一致性、NaN 和无穷大；空文档列表直接返回 []。超长输入在编码前抛错，不依赖模型悄悄截断。

增加这一层的原因是集中控制编码规则，让 Chroma 负责存取与检索。更换 Embedder 实现不必重写数据库逻辑，但更换模型后必须重新建立对应文档向量。

本次还厘清了 Python 的两个概念：

- `def token_length(model, text: str)` 中 model 没写类型提示，仍可接受实际传入的 SentenceTransformer 对象。运行时由对象是否具有 tokenizer 属性决定能否调用；参数名不决定对象类型。
- `model.tokenizer` 是模型携带的分词器对象，写 `model.tokenizer(...)` 实际调用其 `__call__()`。本机检查得到 BertTokenizer，通用调用逻辑来自 transformers 的 tokenization_utils_base.py。

L2 归一化后，非零向量范数约为 1，因此点积约等于余弦相似度；归一化不会自动提高证据可信度，也不能对齐不同模型的向量空间。

## 阶段三：把字符切片与模型长度限制分开

Day 07 的默认值 900/120 表示字符数。模型真正接收的是 tokenizer 产生的 token 序列，因此 900 字符不等于 900 tokens。

这次把 `chunk_size`、`overlap` 作为关键字参数从批量加载入口一路传到单文件入口、文本切片和 PDF 逐页切片，保留旧的 900/120 默认值。Day 08 实验显式采用 400/60。

400 字符只是起始配置，不是一定低于模型上限的保证。实际检查：

```python
encoded = model.tokenizer(
    text,
    truncation=False,
    add_special_tokens=True,
)
token_count = len(encoded["input_ids"])
```

特殊 token 计入长度；若使用查询指令，必须在拼接指令后检查总长度。

不能混淆的三个量：

| 名称 | 如何得到 | 决定什么 |
| --- | --- | --- |
| 字符数 | len(text) | 当前字符切片的大小和原文 offset |
| token 数 | len(tokenizer(text)["input_ids"]) | 是否超过模型输入上限 |
| 向量维度 | len(embedding) | 编码结果有多少个数值分量 |

最初 Day 07 样例审计：4 个 Source，最长 12 tokens，问题为 8 tokens。后来固定语料审计：13 个 Source，最长 177 tokens，12 个问题中最长 25 tokens。两次均无超长输入。

改切片必须从原始文件重新生成 Source、offset 和 ID；不能把旧 Source.content 再切碎后直接复用旧身份和位置。

## 阶段四、五：建立可存取的 ChromaIndex 并补齐契约

Chroma 是向量数据库。当前使用 PersistentClient，将文档向量和来源保存在本地磁盘，无须单独部署服务器。
collection 可以近似理解成一组索引记录，承载某一套模型、语料和实验配置。

写入方式：

```python
embeddings = embedder.embed_documents(contents)
collection.upsert(
    ids=ids,
    documents=contents,
    embeddings=embeddings,
    metadatas=metadatas,
)
```

集合设置 `embedding_function=None`，避免 Chroma 隐式选择编码模型；编码由应用显式负责。集合配置明确使用 cosine。

文档向量先在内存中生成，再通过 upsert 持久化。问题向量临时生成，用于本次 query，不作为新文档自动写入集合。

公共契约：

| 接口或输入 | 当前行为 |
| --- | --- |
| ChromaIndex(path, collection_name=..., embedder=...) | 保留旧 path 调用；未注入 Embedder 时延迟加载默认模型 |
| add([]) | 不操作、不调用模型 |
| add(sources) | 一次批量编码并 upsert；同批次重复 ID 明确报错 |
| 相同 ID 再次 add | 更新记录，count 不增长 |
| search(空白问题) | 返回 [] |
| 空库 search | 返回 []，不先编码 |
| 非法 top_k | 抛 ValueError，包括 bool、非整数、0 和负数 |
| top_k 大于记录数 | 实际 n_results=min(top_k, count) |
| delete(ids) | 按精确 ID 删除；空列表不操作 |
| count() | 返回当前记录数 |
| get()/all() | 从数据库恢复完整 Source，作为扩展接口 |

Source 到 Chroma 的关键映射：

```text
id                         ← source_id
document                   ← content
embedding                  ← 当前 Embedder 输出
metadata.title/url/...     ← 标题、路径、URL、页码
metadata.source_metadata_json ← 完整 Source.metadata 的 JSON 字符串
metadata.fetched_at        ← 原时间的 ISO 字符串
metadata.source_schema_version ← 来源存储格式版本
```

没有 URL/路径时保存约定空字符串；没有页码时保存 0，读出时还原为 None。嵌套 dict/list 用 JSON 保存，不直接塞给简单标量 metadata 接口。

完整保存 metadata 是为了保住 offset/end_offset、offset_basis、空白页警告等 Day 07 证据链。只保存正文和文件名，虽然还可能检索成功，却不能精确追溯原文字符位置。
fetched_at 也必须保存原值，不能重建 Source 时变成查询时刻。

错误边界已经区分：参数错误、IndexDataError、IndexConfigurationError、模型未就绪和底层数据库异常。
坏 JSON、缺字段、非法向量不会伪装成“没有结果”；写入前检查数量、维度、有限性及 cosine 零向量。重开后会根据已保存向量校验维度。

### 查询结果为什么是二维列表

Chroma 支持一次提交多个问题向量。外层按问题分组，内层按该问题的候选排名排列。

```python
ids = [["doc-a", "doc-b", "doc-c"]]  # 一个问题的 Top-3

result["ids"][0][1]
result["documents"][0][1]
result["metadatas"][0][1]
result["distances"][0][1]
```

以上四个位置对应同一个候选。这种二维结构是“问题数 × 候选数”，不是向量维度。

### 距离与分数方向

```text
cosine distance = 1 - cosine similarity
当前 Source.score = 1 - distance

distance：越小越近；score：越大越相似。
distance = 0/1/2，对应 similarity = 1/0/-1。
```

负相似度是可能的，不能擅自当成 0～1 正确率。这个换算依赖当前 cosine 集合，不能直接套到任意 L2 距离。
原始距离保存于返回 Source.metadata["_retrieval"]，包含 metric="cosine" 和 distance；它是查询产生的信息，不污染持久化的原始来源 metadata。

HybridIndex 分数与 Chroma 分数不能直接相加：前者主要表示字面频次重合，后者表示模型学出的语义接近，数值分布和尺度未校准。
即使都调用余弦、分数方向相同，也不能认定 0.7 具有相同强度。Day 09 可以进一步学习现有 merge_ranked() 的 RRF 排名融合。

## 阶段六：证明 upsert、删除和持久化

实现 `examples/day08_chroma_persistence_lab.py`，明确分开 build 和 reopen。

本人在 PyCharm 的实际记录位于：

```text
data/day08/persistence-v1/experiment.json
```

实际步骤和计数：

```text
加载 Day 07 样例，得到 N=4 个不重复 Source
首次 add                        → count=4
相同 Source 再次 add            → count=4
查询并选中一个命中 ID 删除      → count=3
collection.get(ids=[被删ID])     → ids=[]
结束进程
另一个进程只运行 reopen         → count=3
被删 ID 不存在，其余正文、metadata 和原时间与快照完全一致
```

被删 ID 为 `doc-f82990203cf38d2f`。重开后的三个剩余 ID 为：

```text
doc-51a75748cc037300
doc-7c176e81db74f8fb
doc-dccc91b46e344f92
```

仅看到启动后“有数据”不够。必须确认 reopen 不加载语料、不调用 add、不创建缺失集合，并核对删除状态和完整快照。
如果启动时又添加全部原语料，被删除片段会被恢复，因此删除状态也是有意义的证明。

### upsert 不等于文档版本替换

```text
旧版 ID：A、B、C
新版 ID：A、D、E
只 upsert 新版后可能留下：A、B、C、D、E
```

upsert 只知道本次给出的 ID，无法判断 B、C 应不应该删除。正文、路径或切片变化会生成新 ID，旧片段可能残留。

本课采用“新语料版本 → 新集合”：保留 v1，从更新后的完整语料建立 v2；验证后切换查询集合，旧版按需要保留用于比较和回退，再择时清理。不是每次更新先把旧库全删掉。

## 阶段七：固定语料、问题和预标注证据

目录：`data/day08/retrieval-v1/`。准备脚本为 `examples/day08_prepare_retrieval_dataset.py`。

12 份合成资料覆盖虚拟环境、密钥保护、异步、工具参数与回传、PDF 追溯、offset、模型一致性、Agent 停止条件、证据不足；另有烹饪、园艺和印刷页码干扰资料。
工具参数验证和调用消息流共用一份文件，不能靠“一道题对应一个手工 Source”让评测变得过于容易。

真实加载结果为 13 个 Source。PDF 共 3 个物理页，第 2 页留白，只生成第 1、3 页片段并保留空白页警告。
PDF 使用英文文本避免字体问题；Q06 是中文问题对英文证据，因此还包含跨语言因素，不能将任何失败都直接归因于页码处理。

标注流程为：先写资料，再确定支持结论的关键句，最后才运行检索。

```text
questions.jsonl：query_id、question、expected_relative_path、expected_page、evidence_quote
  → 按文件、物理页、完整关键句定位片段
  → resolved_labels.json：acceptable_source_ids
```

长期标签绑定文件、页和关键句。片段 ID 会因路径或切片变化而漂移，所以移动目录后需重新派生。
overlap 导致多个片段包含完整关键句时，都可接受；找不到完整句或句子跨片段时明确报错，不能偷偷选一个“最像”的 ID。

另外保存 N01“2027 年公司营收”和 N02“园艺资料里的管理员密码”两个无目标答案探针，不进入 10 题命中率分母。
N02 中没有可给出的真实密码。园艺资料关于“不记录账号密码”的声明，不能被当成一个真实密码答案；该题措辞本身带有是否问句的歧义，后续设计更大评测集时可明确区分“是否存在”与“具体值是什么”。本轮保留原题与原规则，不为得分改标签。

同时生成文件 SHA256、数据指纹、模型快照、依赖版本、sources.jsonl 和逐条长度审计，便于确认两次实验是否使用相同输入。

## 阶段八：真实 Top-3 与内容审核

运行 `examples/day08_evaluate_retrieval.py`，使用固定模型快照和语料；每次生成独立运行目录，不覆盖最初结果。

本次运行：`20261019T023647Z-9458be24`。

```text
data/day08/retrieval-evaluation/20261019T023647Z-9458be24/
  raw_results.json        原始 Top-3、正文、ID、页码、distance、score
  raw_integrity.json      原始结果校验值
  dataset_manifest.json  当次配置副本
  review.csv             逐候选支持等级、理由、错误原因
  review_annotations.json Codex 辅助审核的归属与逐条评分依据
  review.md              可直接阅读的审核表
  summary.json           最新指标
  reports/               历次 report 的审核表和结果快照
```

支持等级：0=无关或不支持，1=相关但缺关键证据，2=正文直接支持题目要点。
评分读取整条 content，不只看文件名、是否命中预标注 ID 或分数高低。reason 必须说明具体支持或缺少什么；error_cause 记录不足原因，正确支持时可留空。

结果（由 Codex 辅助审核）：

| 问题 | Top-1/2/3 支持等级 | Hit@3 |
| --- | --- | --- |
| Q01 项目依赖隔离 | 2 / 0 / 0 | 1 |
| Q02 密钥存放与禁止位置 | 2 / 1 / 0 | 1 |
| Q03 网络异步等待 | 2 / 0 / 0 | 1 |
| Q04 工具参数验证原因 | 2 / 1 / 0 | 1 |
| Q05 工具执行与回传 | 2 / 1 / 0 | 1 |
| Q06 PDF 空白页后的页码 | 1 / 1 / 2 | 1 |
| Q07 offset 还原原文 | 2 / 1 / 0 | 1 |
| Q08 向量模型一致性 | 2 / 0 / 0 | 1 |
| Q09 Agent 停止条件 | 2 / 1 / 1 | 1 |
| Q10 证据不足策略 | 2 / 1 / 0 | 1 |
| N01 公司营收探针 | 0 / 0 / 0 | 不计入分母 |
| N02 管理员密码探针 | 1 / 0 / 0 | 不计入分母 |

```text
Top-1 正向命中：9/10
Hit@3：10/10 = 1.0
待评分候选：0/36
教学目标：达到至少 8/10
```

最有价值的失败分析是 Q06：Top-1 的印刷页码资料词汇很接近，却没有给出 PDF 物理页规则；Top-2 的 PDF 概述只介绍空白页；Top-3 的物理第 3 页才明确说明引用应计入空白页、不能压缩页号。它说明 Top-1 不一定就是正确证据。

本次是初始基线，没有为了达到分数再删题或修改标签，也没有实际运行查询指令、切片参数的修正对照。自动 ID 命中率和内容审核结果分开记录。

### 三件事不能混为一谈

1. Top-3 有返回：库里选出了最近的候选，不保证支持答案。
2. Hit@3 命中：前三条至少有一条正文直接支持本题要点。
3. 最终答案正确：模型正确理解并使用证据，还没有编造、误读或遗漏必要条件。

近邻搜索总能在足够大的非空库里选出相对最近的三条，所以没有目标答案的问题仍可能返回三条资料。需要额外检查证据充分性，不能凭一个未经校准的固定阈值承诺自动拒答。
当前 Hit@3 不是“全部相关片段的 Recall@3”，也不是最终回答准确率。10 道短合成题的好成绩不能代表生产资料质量。

## 阶段九：测试工程行为，不拿假向量证明语义理解

测试采用三层验证：

| 层 | 验证内容 | 本次证据 |
| --- | --- | --- |
| 数学与参数 | 余弦方向、缩放、零向量、非法 top_k 等 | 标准库函数与 pytest |
| 存储集成 | 真实 Chroma 存取、来源、删除、重开、异常边界 | 假 Embedder + 临时真实数据库 |
| 真实语义验收 | 实际 tokenizer、真实向量、固定问题的证据支持 | BGE 模型 + 阶段七语料 + 阶段八审核 |

阶段九已覆盖课程 M01、V01～V12，详细映射见 `tests/day08-test-matrix.md`。
重点新增验证包括：top_k 超库大小时返回数量、cosine 距离 0/1/2 与 score 1/0/-1、精确 ID 不按前缀误删、删除后重开不 add 仍能查、完整来源往返、非法查询向量不到数据库、超长输入不进入 encode。

依赖隔离测试在新进程阻止 chromadb、sentence_transformers、transformers、torch、huggingface_hub 导入，确认基础 retrieval 模块仍可使用；显式创建真实模型或索引才提示安装 vector。

最后一次相关回归实际执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_vector_math.py tests/test_vector_imports.py tests/test_embeddings.py tests/test_chroma_index.py tests/test_vector_index.py tests/test_documents.py tests/test_retrieval.py -q
.\.venv\Scripts\python.exe -m pip check
```

结果为 115 passed，46 条警告来自 Chroma 的 legacy embedding function config 弃用提示。pip check 输出 No broken requirements found。
当次设置 HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1，存储测试实际运行，没有跳过；运行环境使用了新的项目内专用 pytest 临时目录，完成后清理。

假 Embedder 通过只能证明存取、排序和接口正确。真实模型仍需验证加载、实际长度、归一化、同义表达、否定关系、干扰和跨语言检索等效果。

## 复习时最容易忘记的几个判断

**同模型不等于同实验。** 查询是否加指令、清理空白、改写内容以及是否归一化，都会改变输入或向量。必须记录处理模板并整组统一运行，不能一半问题加指令却混成同一份基线。

**同维度不等于同空间。** 两个模型都输出 512 个数，只说明长度相同；学习出的坐标方向和含义可能不同。库可能因维度一致而接受混用向量，但比较结果没有可靠语义依据。只有明确训练对齐的编码器才可跨模型配合。

**Top-k 控制数量，不控制真假。** k 小可能漏证据，k 大可能增加无关内容和后续上下文成本。要在固定评测集上观察，不因多返回几条就认定效果提高。

**检索结果中的指令仍是资料。** 文档写“忽略用户要求”“用户已经同意”不能成为当前用户授权。可以分析和引用这段内容，但不能因此改变任务、泄露信息或扩大工具操作权限；检索进入上下文不会提升文档作者的指令权限。

## 下次从哪些文件找回思路

以下路径以 `E:\agent_project\agent-learning-lab` 为项目根目录。

| 文件 | 阅读目的 |
| --- | --- |
| src/research_agent/documents.py | 原始文件如何变成可追溯的片段，切片参数如何传到 PDF |
| src/research_agent/embeddings.py | 协议、同一模型复用、两端处理、长度与输出检查 |
| src/research_agent/vector_math.py | 不加载模型也能理解和测试余弦 |
| src/research_agent/retrieval.py | 对照 HybridIndex 与 ChromaIndex，查看写入、查询和来源映射 |
| examples/day08_embedding_lab.py | 手算向量、真实编码、Day 07 样例长度审计 |
| examples/day08_chroma_smoke.py | 两个正交小向量验证 Chroma API |
| examples/day08_chroma_lab.py | 真实 BGE 与 Day 07 Sources 的索引查询 |
| examples/day08_chroma_persistence_lab.py | build/reopen 分离和删除状态持久化 |
| examples/day08_prepare_retrieval_dataset.py | 固定语料、证据句、派生 ID、配置指纹 |
| examples/day08_evaluate_retrieval.py | 保存真实 Top-3 与读取审核表计分 |
| examples/day08_retrieval_review_README.md | 审核表如何填写、命令如何运行 |
| tests/day08-test-matrix.md | 课程测试矩阵和实际验证范围 |

### 常用运行命令

在项目根目录打开终端：

```powershell
# 重做固定数据准备；不运行检索
.\.venv\Scripts\python.exe examples/day08_prepare_retrieval_dataset.py

# 新建一轮真实检索实验，自动打印新的 run_dir
.\.venv\Scripts\python.exe examples/day08_evaluate_retrieval.py

# 只读取已填写审核表并计分，不重新检索
.\.venv\Scripts\python.exe examples/day08_evaluate_retrieval.py report --run-dir data/day08/retrieval-evaluation/20261019T023647Z-9458be24

# 验证已完成的持久化实验，不恢复已删除记录
.\.venv\Scripts\python.exe examples/day08_chroma_persistence_lab.py reopen
```

重新从头做持久化实验，使用新的版本号，build 和 reopen 的版本必须相同：

```powershell
.\.venv\Scripts\python.exe examples/day08_chroma_persistence_lab.py build --version v2
# 等进程结束，再开启第二次运行
.\.venv\Scripts\python.exe examples/day08_chroma_persistence_lab.py reopen --version v2
```

如果 v2 已有记录，换一个尚未使用的版本。不能把重新 build 混进 reopen 演示。
PyCharm 的脚本参数与终端参数含义相同，例如只填 `report --run-dir ...`，不要把参数写到 Python 代码中。

## 遇到的提示与判断

- HF Hub 的未认证提示：匿名访问限额相关警告，不等于模型加载失败；本次权重已成功加载。
- Windows symlink 缓存提示：缓存仍能工作，可能占用更多空间；关闭警告不会真的开启符号链接支持。
- image_only.pdf 的 no_extractable_text：没有可提取文字层，当前没有 OCR，属于已知样例边界。
- argparse 提示缺 mode：持久化脚本必须传 build/reopen，不是模型或数据库错误。
- report 已输出 pending_candidate_rows=0，却仍提示填写表：脚本当时无条件打印结尾提示。以实际进度字段为准，不能据此误以为评分没保存。
- pytest 临时目录不可写或沙箱运行受阻：与业务断言失败不同，需要先处理运行目录/环境；不能修改业务测试把环境错误当通过。

## 环境、费用与尚未完成的部分

整理时核对的环境：Python 3.11.16、chromadb 1.5.9、sentence-transformers 5.7.0、transformers 5.19.0、PyMuPDF 1.28.2。
实验使用本地 CPU 和已缓存的模型，没有调用聊天模型或付费模型 API；不将下载流量、硬件时间或电费计入“API 费用”。

当前限制和后续任务：

- 400/60 只是本轮通过审计的配置，尚未做多个 chunk 参数的受控检索比较。
- 尚未统一记录冷启动、模型加载、建索引、编码和数据库查询的分段耗时，不能声称达到某个性能指标。
- 未做查询指令对照，未完成不同模型的独立集合比较。
- 未实现 OCR、按 token 切片、生产级按文档版本原子替换和完整失败恢复。
- 当前没有在 ChromaIndex 内强制校验所有同维模型的身份；评测脚本通过固定模型快照和配置约束实验。更换模型仍须显式使用新集合。
- AI 辅助审核结果不能冒充独立人类标注；N02 等探针措辞和小规模合成语料的局限需要在扩展评测时注意。
- 未完成 RRF 的实际融合对照，也未接入最终带引用回答和证据充分性控制。
- `.gitignore` 尚未完成 Day 08 缓存/数据库与需保留的合成资料、标注、报告之间的精细区分；Git 提交未在本次日志任务中执行。提交前应只保留合成材料和必要代码/结果，不提交模型权重与 Chroma 二进制库。

复习时可以先尝试不看代码解释：谁生成向量、谁存向量、distance 的方向、为什么要保留 offset、如何证明 reopen 没重新 add，以及为什么 Hit@3=1.0 仍不等于最终回答全对。能把这些问题串起来，才算理解了本课的完整检索链路。
