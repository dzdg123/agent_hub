# Day 08：Embedding 与向量检索——PyCharm 详细学习计划

> 项目：`E:\agent_project\agent-learning-lab`  
> 环境：PyCharm + 项目 `.venv` 中的 Python 3.11  
> 学习投入：当天总计 8 小时，各阶段弹性安排  
> 主线：Source → 文本向量 → 本地 Chroma 索引 → 问题向量 → Top-k → 原文与来源 → 人工验证

## 1. 对齐六周项目计划总览

本计划依据六周总览“第 8 天：Embedding 与向量检索”，并对齐项目 `curriculum/week-02.md` 的 Day 8。延续 Day 07 的本地文档链路，今天完成可解释、可持久化、可验证的向量检索。

| 总览要求 | 今天的具体交付 |
|---|---|
| 理解向量、Embedding、余弦相似度、Top-k | 手算小向量实验、真实中文 Embedding 实验、口头讲解 |
| 选择适合 CPU 的小型中文模型 | 复用项目选择的 BAAI/bge-small-zh-v1.5，记录实际耗时与配置 |
| 使用 Chroma 建立本地索引 | 在独立实验目录完成写入、查询、删除、重启读取 |
| 文档切片与检索 | 沿用 Day 07 Source 与来源坐标，检查模型输入长度 |
| 建立 10 个检索问题 | 固定题目、预先标注证据、Top-3 人工判断表 |
| 相关内容通常进入 Top-3 | 计算 Hit@3；教学目标至少 8/10，不把未达标结果隐藏 |
| 扩展比较 Chunk 大小 | 相同语料、相同问题、不同独立集合的受控对照 |

今天先完成“检索到证据”，Day 09 再比较、融合检索方式，Day 10 再生成带引用回答。

## 2. 今天最重要的工程判断

对研究 Agent 而言，检索器决定模型能看到哪些资料。检索阶段漏掉关键证据，后面再精巧的 Prompt 也不能凭空补齐事实。

今天需要建立五个判断：

1. **Embedding 是模型计算出的数字表示。**它不是摘要，也不是把事实存入大模型权重；向量的单个维度通常没有可以直接命名的业务含义。
2. **向量相近表示模型认为某些特征相似。**不保证两段话事实一致，更不保证它们支持问题的答案。
3. **检索返回候选证据。**Top-3 是排序后的最多三个候选，不是三个正确答案。
4. **向量索引必须保存来源。**只取回文本却丢掉文件、页码与 offset，会破坏 Day 07 建立的追溯链。
5. **先看输入，再调检索。**如果 PDF 文字提取错误、长片段被截断、来源标签错误，先修数据与契约。

本课不需要 DeepSeek API。首次下载模型需要网络；模型缓存就绪后，用本地资料完成实验，不产生模型 API 调用费用。

## 3. 弹性学习规则与今日交付

每天只固定 8 小时总投入，不固定各阶段的小时数。按“预测 → 实验 → 解释 → 实现 → 验证”推进。

- 环境安装受阻时，先完成余弦实验、固定语料、评测标签和假向量测试，随后回到真实模型验证。
- 假向量可以验证程序流程，不能替代真实中文语义检索验收。
- 核心完成后再比较 Chunk；核心未完成就记录阻塞原因，先补齐主线。
- 不为提前完成而增加多 Agent、图数据库或部署任务。

今日必须交付：

- [ ] 一张索引阶段与查询阶段的数据流图。
- [ ] 一个真实中文 Embedding 实验，记录维度、输入长度、耗时与相似度。
- [ ] ChromaIndex 的写入、查询、按 ID 删除、持久化读取能力。
- [ ] 向量库存取后仍可回到文件、PDF 页码和规范化文本坐标。
- [ ] 10 个正向检索问题及 Top-3 人工判断表。
- [ ] 2 个无证据探针，解释“返回候选不等于有答案”。
- [ ] 离线行为测试、真实模型集成实验、PyCharm 演示。
- [ ] 学习日志、实际依赖版本记录和 Git 提交。

## 4. 与当前代码和 Day 07 进度衔接

2026-10-13 阅读当前文件得到以下起点；学习时仍先确认自己的工作区是否有更新。

| 当前内容 | 已有能力 | Day 08 重点 |
|---|---|---|
| `documents.py` | TXT/Markdown/PDF 加载、规范化切片、详细批次诊断 | 复用，不重写加载器 |
| Day 07 日志 | 记录了页码、offset 修复及 38 项测试通过 | 这是已有日志记录；今天重新做相关回归 |
| `Source` | 正文、文件、页码、metadata、score | 明确库存取映射与分数含义 |
| `HybridIndex` | 词项频次余弦 + 字符频次余弦，加权排序 | 作为理解相似度的起点，不当成神经语义模型 |
| `ChromaIndex` | PersistentClient、固定 research 集合、模型封装、upsert | 当前只有 add，补 query/delete 与结果还原 |
| 当前 Chroma 元数据 | title、url、file_path、page | 尚未保存 Day 07 完整 metadata |
| `runtime.get_index()` | 默认创建 HybridIndex | 本课独立实验，先不替换整个 Agent 的运行路径 |
| `pyproject.toml` | vector 可选依赖：chromadb>=1,<2；sentence-transformers>=3,<6 | 安装已有扩展，记录实际解析版本 |

`HybridIndex` 的名字不代表它已经实现了下一课要比较的“神经向量检索 + 关键词检索”。它当前混合的是两种频次相似度。`merge_ranked()` 留到 Day 09 深入学习。

## 5. 具体文件操作清单

以下路径均相对于项目根目录。

| 文件/目录 | 操作 | 用途 |
|---|---|---|
| `src/research_agent/retrieval.py` | 核心修改 | 补齐 ChromaIndex 的接口、序列化、查询、删除和输入校验 |
| `src/research_agent/embeddings.py` | 建议新建 | 封装 CPU 模型、文档与问题编码、长度检查；允许注入假实现 |
| `src/research_agent/models.py` | 阅读为主 | 复用 Source，不另造含义相同的数据结构 |
| `src/research_agent/documents.py` | 复用，必要时小改 | 需要实验 Chunk 参数时增加向下兼容的关键字参数 |
| `src/research_agent/runtime.py` | 阅读 | 明白默认索引仍在哪里创建 |
| `tests/test_retrieval.py` | 保留并补充 | 现有频次检索回归、余弦和参数边界 |
| `tests/test_vector_index.py` | 新建 | 假向量 + 临时 Chroma 的存取、删除、持久化测试 |
| `tests/fixtures/day08/corpus/` | 新建 | 自建 TXT/Markdown 语料；放可重复生成 PDF 的脚本或原始文本 |
| `tests/fixtures/day08/queries.json` | 新建 | 固定问题、预先标注的证据位置与关键句 |
| `examples/day08_embedding_lab.py` | 新建 | 模型维度、余弦、长度、编码耗时实验 |
| `examples/day08_vector_lab.py` | 新建 | build/search/delete/reopen 演示 |
| `examples/day08_evaluate.py` | 新建 | 跑固定问题，导出候选与人工判断模板 |
| `curriculum/day-08-log.md` | 新建 | 理解、实验结果、失败分析、限制 |
| `curriculum/day-08-top3-review.md` | 新建 | 人工审核与指标结果 |
| `data/day08/` | 运行生成 | Chroma 数据、生成 PDF、报告、依赖快照；加入 .gitignore |

脚本名称是今天要创建的目标文件，不代表项目现在已有这些命令。先完成脚本，再按后文配置 PyCharm。

## 6. 阶段零：确认解释器与安装扩展

### 6.1 确认环境

打开 PyCharm 的 `agent-learning-lab` 项目，Terminal 工作目录应为项目根目录。继续用现有 `.venv`，不需要重新激活 PowerShell 脚本。

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip --version
.\.venv\Scripts\python.exe -m pytest tests/test_documents.py tests/test_retrieval.py -q
```

先记录测试现状；失败时先判断是昨天未完成、环境问题，还是今天修改引入的回归。

### 6.2 安装已有的 vector 可选依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[vector,dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import chromadb, sentence_transformers; print(chromadb.__version__); print(sentence_transformers.__version__)"
```

项目已经声明依赖范围，不再另加一组互相冲突的版本约束。首次安装可能拉取 PyTorch 等较大依赖；保留终端输出，遇错按包名和报错定位，不重复创建虚拟环境。

安装完成后记录实际版本。项目今天不做全量依赖锁定，保留一份环境快照供排错：

```powershell
New-Item -ItemType Directory -Force data/day08
.\.venv\Scripts\python.exe -m pip freeze | Set-Content -Encoding utf8 data/day08/environment.txt
```

检查点：PyCharm 的 Run Configuration 和 Terminal 命令使用同一个 Python 3.11；能导入两个库，已有文档测试没有新增失败。

## 7. 阶段一：先把“向量相似”算明白

### 7.1 五个概念

| 概念 | 小白可以怎样理解 | 必须避免的误解 |
|---|---|---|
| 向量 | 一列按固定顺序排列的数字 | 并非任意数字拼起来就有语义 |
| Embedding | 模型把文本映射为固定维度向量 | 不是文本摘要，不是聊天回复 |
| 余弦相似度 | 比较两个向量方向是否接近 | 不是“答案正确的概率” |
| 向量索引 | 帮助从很多向量中查找近邻 | 不负责自动判断资料真假 |
| Top-k | 返回排序最靠前的最多 k 个候选 | k 越大不代表回答质量越好 |

公式先理解各部分，再运行代码：

```text
cos(a, b) = dot(a, b) / (norm(a) * norm(b))

dot：同位置的数相乘后求和
norm：各分量平方求和后开根号
```

在 `examples/day08_embedding_lab.py` 写一段独立小实验：

```python
from math import sqrt


def cosine(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        raise ValueError("向量不能为空且维度必须一致")
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        raise ValueError("零向量不能计算余弦相似度")
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


print(cosine([1, 0], [1, 0]))
print(cosine([1, 0], [0, 1]))
print(cosine([1, 0], [-1, 0]))
print(cosine([1, 0], [10, 0]))
```

先预测四行输出，再解释为什么向量长度增大十倍没有改变方向相似度。生产入口还应拒绝 NaN、无穷大等非有限数，不能把异常数值写入索引。

### 7.2 对照 HybridIndex

阅读 `tokenize()`、`_cosine()` 和 `HybridIndex.search()`：

1. Counter 是什么？每个维度由哪个词项或字符决定？
2. 0.7 与 0.3 是人工设置的权重，还是模型学出来的？
3. “汽车”和“轿车”没有相同字时，频次检索为何可能漏掉？
4. 为什么两个词汇相近但事实相反的句子可能得高分？

检查点：能说清“余弦是一种比较方式，Embedding 是表示的生成方式”，两者不是同一件事。

## 8. 阶段二：运行真实中文 Embedding

### 8.1 沿用项目模型

使用 `BAAI/bge-small-zh-v1.5`，显式 `device="cpu"`。模型卡列出的中文 small 模型输出为 512 维；在代码中仍用实际输出形状核验，不靠硬编码猜测。选择它是为了沿用项目并控制本地实验规模，效果由你的语料验证。[模型作者说明](https://huggingface.co/BAAI/bge-small-zh-v1.5)

在实验脚本中运行：

```python
from time import perf_counter

from sentence_transformers import SentenceTransformer

started = perf_counter()
model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
print("load_seconds:", perf_counter() - started)
print("max_seq_length:", model.max_seq_length)

texts = [
    "汽车需要定期保养发动机。",
    "轿车应按周期检查和维护引擎。",
    "番茄炒蛋需要准备鸡蛋和番茄。",
]
started = perf_counter()
vectors = model.encode(texts, normalize_embeddings=True)
print("shape:", vectors.shape)
print("encode_seconds:", perf_counter() - started)
print("similarities:", vectors @ vectors.T)
print("first_values:", vectors[0][:8])
```

记录：加载耗时、第二次加载耗时、三段编码耗时、shape、两组相似度。相似度顺序先预测，实际不符合预期时如实解释，不写死演示分数。

模型加载包含下载/缓存/初始化，编码耗时包含本地推理，两者分开记录。CPU 推理不因为写成 async 就自动变快。

### 8.2 统一编码规则

建议在 `embeddings.py` 提供：

```python
from typing import Protocol


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...
```

真实实现复用同一个已加载的 SentenceTransformer 对象，不每次查询都重新加载；输出统一转换为 Python float 列表。空文本、空问题、输出维度不一致有明确错误，空列表文档输入返回空列表。

基线约定：文档直接编码正文；问题直接编码问题；两者均做 L2 归一化。查询指令属于可选实验：如采用模型作者推荐的检索指令，只加在问题端，记录模板，重跑完整评测。不要一半查询加指令、一半不加，却混成同一份基线。

模型、版本/模型快照、归一化、查询指令、切片配置共同决定检索实验。即使两个模型维度相同，也不能混用它们生成的向量。

## 9. 阶段三：处理 Chunk 与模型长度限制

Day 07 默认按字符切片，chunk_size=900、overlap=120；模型按 tokenizer 的 token 序列读取。**900 个字符不等于 900 个 token。**过长文本可能在编码时截断，而库中保存的正文仍然是完整片段，容易造成“后半段明明存在却检索不到”。

今天先做长度审计：

```python
token_lengths = [
    len(model.tokenizer(text, truncation=False)["input_ids"])
    for text in texts
]
print("token_lengths:", token_lengths)
print("model_limit:", model.max_seq_length)
```

对实际 Source 全量统计最大长度和超长片段数。特殊 token 和问题指令也占长度。检查问题端长度；不要让超长输入静默通过。

处理顺序：

1. 小型基线语料每篇控制为短段落，先让真实检索完整跑通。
2. 对长文先试 chunk_size=400、overlap=60，再做 token 审计；这只是起始参数，不是长度安全保证。
3. 如仍超长，缩小切片并重新审计，或将按 token 切片列为后续任务。
4. 如果需要修改加载器，在 load_document 与 PDF 路径中向下传递关键字参数，保留原默认值；不要只改文本路径而遗漏 PDF。
5. 继续使用 Day 07 的规范化原文坐标。不能把旧 Source.content 二次切碎后直接复用旧 offset 和 ID。

检查点：所索引片段在当前模型长度范围内；能解释字符数、token 数、向量维度分别是什么。

## 10. 阶段四：先看懂 Chroma 的存取机制

### 10.1 今天采用的结构

为了看见每一步，建议让应用显式生成 embeddings，再交给 Chroma：

```text
索引阶段
文件 → Day 07 loader → Source[] → embed_documents(contents)
    → collection.upsert(ids, documents, embeddings, metadatas)

查询阶段
问题 → embed_query(query) → collection.query(query_embeddings)
    → ids / documents / metadatas / distances → Source[]
```

这样可以注入假 Embedder 做离线测试，并且避免实验中不小心触发 Chroma 默认模型下载。现有 SentenceTransformerEmbeddingFunction 封装也能使用；若沿用它，要确认问题和文档预处理以及测试替身如何控制。选定一条主线，不让同一批数据重复编码。

官方文档说明同时传 documents 与 embeddings 时可保存两者而不重新编码。[Chroma 写入文档](https://docs.trychroma.com/docs/collections/add-data)

### 10.2 在独立目录建立集合

先用下面片段理解 API，再迁移到 ChromaIndex。代码中的小向量用于验证库操作；真实语义实验换成 Embedder 输出。

```python
import chromadb

client = chromadb.PersistentClient(path="data/day08/chroma-smoke")
collection = client.get_or_create_collection(
    name="day08-smoke-cosine-v1",
    embedding_function=None,
    configuration={"hnsw": {"space": "cosine"}},
)
collection.upsert(
    ids=["smoke-agent", "smoke-food"],
    documents=["Agent 使用模型和工具完成任务。", "番茄炒蛋是一道菜。"],
    embeddings=[[1.0, 0.0], [0.0, 1.0]],
    metadatas=[{"topic": "agent"}, {"topic": "food"}],
)
result = collection.query(
    query_embeddings=[[1.0, 0.0]],
    n_results=2,
    include=["documents", "metadatas", "distances"],
)
print(result)
```

这里显式选择 cosine 距离；当前官方文档用 configuration 配置集合。已有集合不会因为 get_or_create 时换参数就自动重建，实验变更应使用新集合名，并核对实际配置。[Chroma 集合配置](https://docs.trychroma.com/docs/collections/configure)

写出结果数组对应关系。一次问题查询的 ids[0]、documents[0]、metadatas[0]、distances[0] 逐位置对应；多问题查询外层才有多组。[Chroma 查询返回结构](https://docs.trychroma.com/docs/querying-collections/query-and-get)

## 11. 阶段五：补齐 ChromaIndex 的工程契约

### 11.1 公共接口与兼容性

保留当前 add(sources) 名称与 upsert 行为，构造器增加可选 collection_name、embedder 或等效配置；保留旧 path 调用方式。今天至少实现：

| 接口 | 约定 |
|---|---|
| `add(sources)` | 批量编码并 upsert；空列表不调用模型 |
| `search(query, top_k=5)` | 返回 list[Source]；空白 query 返回 [] |
| `delete(source_ids)` | 按精确 ID 删除；空列表不操作 |
| `count()` | 返回当前记录数，方便验证幂等写入与删除 |

top_k 必须是正整数，拒绝 bool；非法值抛 ValueError。空库直接返回 []，不先编码；实际 n_results 取 min(top_k, count)。重复输入 ID 应去重或明确报错，不能把冲突批次直接交给库碰运气。

不要为了本课强行把 runtime 的默认索引替换为 Chroma；先保证独立索引的接口、测试和配置完整。all/get 的统一接口及运行时可切换作为扩展。

### 11.2 保留完整来源信息

当前 add 只保存少量字段，会丢失 offset 等 Day 07 元数据。建议建立明确的 Source ↔ Chroma 映射：

| Chroma 字段 | 保存内容 |
|---|---|
| id | Source.source_id |
| document | Source.content |
| embedding | 当前模型生成的向量 |
| metadata.title | Source.title |
| metadata.file_path / url | 路径或 URL；无值用约定的空字符串 |
| metadata.page | PDF 物理页；无页码用约定的 0 |
| metadata.source_metadata_json | Source.metadata 的 JSON 字符串 |
| metadata.fetched_at | 原时间的 ISO 字符串，避免重建时变成查询时间 |
| metadata.relative_path / file_type | 如需要未来过滤，可额外保存为简单标量 |

为兼容当前项目依赖范围，本课使用字符串、数值、布尔这些简单 metadata 值；嵌套 dict/list 放进 JSON 字符串，不把 None 直接塞入。取回时 JSON 解析还原，page=0 还原为 None。保留空白页警告等 metadata，不能只挑几个看起来重要的字段。

JSON 破损、缺字段、向量维度不一致应报告索引数据或配置错误，不应伪装成“没有找到”。默认实验集合用新名字，避免旧 research 集合没有新增字段时引入隐式兼容问题。

### 11.3 距离与 score

在本课明确使用 cosine 集合的前提下：distance 越小越近；可令 Source.score = 1 - distance，越大越相似。原始距离也保存在返回 Source.metadata 的独立检索字段中，并标明 metric。该换算不适用于随意换成 L2 后的分数。[Chroma 距离定义](https://docs.trychroma.com/docs/collections/configure)

分数不是 0～1 的正确率；余弦理论上可为负。不要为了看起来整齐就把分数转成“答案可信度 92%”，也不要与 HybridIndex 的分数直接相加。跨方法融合留到 Day 09。

### 11.4 错误边界

- 缺可选依赖：明确提示安装 vector。
- 模型下载失败：保留底层原因，说明模型未就绪。
- 模型输出数量、维度或有限性异常：写入前拒绝。
- 查询/存储失败：明确失败，不捕获所有异常后返回 []。
- 空库、空问题：正常的空结果。
- 参数非法：调用者错误。

先在小语料批量写入，不增加无限重试和复杂并发。保存“本批失败”与原因；不能假定所有批次都具有应用级事务保证。

## 12. 阶段六：验证写入、删除和持久化

按照下面顺序做真实 Chroma 实验，并保存计数与 ID：

1. 用新的专用目录与集合写入 N 个不重复 Source，count=N。
2. 相同 Source 再写一次，count 仍为 N，说明 upsert 不重复累加。
3. 查询一个明确主题，打印前三条正文、ID、文件、页码、score 与距离。
4. 选择一个检索命中的 ID，调用 delete([id])，count=N-1。
5. 用 collection.get(ids=[id]) 确认该 ID 不存在；再查询时也不应出现它。
6. 停止 PyCharm 进程；重新运行，仅打开同一路径与集合，不重新加载语料/add。
7. count 仍为 N-1，删除的 ID 不恢复，其余文本与元数据仍存在。

删除之后需要恢复评测语料时，显式重新 build，并记录恢复动作。不要在 reopen 演示中自动 add，否则无法证明持久化真正成功。

注意：upsert 新 Source 不会自动清理旧 Source。内容、路径或切片参数改变会产生新 ID，旧片段可能仍在库里。今天采用“新语料版本 → 新集合”的简单策略；按文档替换时清理旧 ID 是扩展。[Chroma 删除接口](https://docs.trychroma.com/docs/collections/delete-data)

## 13. 阶段七：准备固定语料和 10 个检索问题

### 13.1 先写资料，再标注，再运行检索

准备约 8～12 份短小合成资料，最终至少 12 个片段，避免只有三个片段时 Top-3 自动全覆盖。纳入无关干扰资料，如烹饪、园艺。TXT、Markdown、文本型 PDF 均经过 Day 07 加载器，不直接给每道题手工构造唯一 Source。

建议主题：虚拟环境、API 密钥、异步并发、工具参数验证、工具返回消息、PDF 物理页码、规范化 offset、向量模型一致性、Agent 停止条件、证据不足策略。PDF 可沿用 Day 07 的生成方法；中文字体不方便时先用英文正文验证页码另做中文检索，不把字体问题扩大为 OCR 任务。

每份资料写清支持结论的关键句，不把全部考题原句复制成标题。加入近似但不支持的片段，例如讨论“纸质书印刷页码”的内容，用于检验是否真的命中物理页码证据。

### 13.2 固定问题表

下面是建议题目，需对应你实际写出的资料，先标注支持证据再跑模型：

| ID | 问题 | 预期证据主题 | 检验点 |
|---|---|---|---|
| Q01 | 怎样避免不同项目安装的包互相干扰？ | 虚拟环境 | 同义表达 |
| Q02 | 调用模型的密钥应放在哪里，哪些地方不应该出现？ | 密钥保护 | 关键规则 |
| Q03 | 多个网络请求怎样同时等待而不逐个排队？ | 异步 I/O | 意图检索 |
| Q04 | 为什么工具函数执行前要验证参数？ | 工具参数 Schema | 原因证据 |
| Q05 | 模型提出调用工具后，谁执行函数，结果怎样传回？ | Function Calling 消息流 | 流程证据 |
| Q06 | PDF 中间有空白页，后续引用的页数该怎样记录？ | PDF 物理页码 | 页码追溯 |
| Q07 | 怎样利用 offset 与 end_offset 找回片段原文？ | 规范化文本坐标 | 字段与解释 |
| Q08 | 文档与查询为什么不能分别使用两种向量模型？ | 向量空间一致性 | 原理证据 |
| Q09 | 如何避免 Agent 一直调用工具而不结束？ | 最大步数与停止条件 | 同义表达 |
| Q10 | 资料没有支持结论时，研究系统应怎样处理？ | 证据不足 | 规则与边界 |

每题标注：query_id、question、expected_relative_path、expected_page（文本可为空）、必须出现且能支持问题的 evidence_quote；切片后再派生 acceptable_source_ids。若一题需要两条证据，提前明确两条分别支持什么。

Chunk 改动会改变 ID，所以长期标签先绑定文件/页/关键句，不只写一个会漂移的 ID。用人工确认的关键句定位片段；若关键句跨片段，标注所需片段组合或明确分级规则。

### 13.3 增加两个无证据探针

另加 N01“本资料里的公司 2027 年营收是多少？”、N02“园艺资料是否说明了数据库管理员密码？”，确认语料中确实没有答案。它们不进入 10 个正向问题的命中率分母。

向量检索仍可能返回三条最相近候选，这是近邻搜索的行为。人工判为不支持并记录。今天不靠未经校准的固定阈值承诺自动拒答；Day 10 再把证据充分性纳入回答流程。

## 14. 阶段八：形成 Top-3 人工判断表

先固定模型和语料，再跑一次并保存原始结果。每条候选都记录：排名、source_id、文件、页码、片段内容、distance、score、是否支持问题、理由。

建议审核表：

| 问题 | 预标注证据 | Top-1/2/3 来源 | 支持等级 | Hit@3 | 错误原因 |
|---|---|---|---|---|---|
| Q01 | 文件/页/关键句 | 实际结果 | 每条分别填 0/1/2 | 0 或 1 | 漏检、截断、相似干扰等 |

支持等级约定：0=无关或不支持；1=主题相关但缺关键证据；2=原文直接支持本题要点。不能因为文件名对了就算命中；必须查看返回片段正文。

```text
Hit@3 = Top-3 中至少有一个直接支持证据的问题数 / 10
```

如果一题预先定义了多条必要证据，另外报告“证据全部覆盖”的情况。Hit@3 不等于严格意义上“全部相关片段的 Recall@3”，也不等于回答准确率。

教学目标：至少 8/10 题命中。未达标时先分析，按顺序检查：

1. 证据是否真的被加载，PDF 是否抽取正确？
2. 原关键句是否被切开或超长截断？
3. 查询与文档是否用同一模型和一致的处理规则？
4. metric 与排序是否搞反？
5. 干扰内容是否词汇相近但不支持？
6. 模型对该类表达是否不足，是否值得做查询指令对照？

保存初始分数和修正后分数；修正不得把失败题删掉或按模型结果改写正确标签。反复优化这 10 题可能过拟合，今天的结果只说明小规模教学语料表现，不能代表生产系统质量。

## 15. 阶段九：编写有意义的测试

### 15.1 三层验证

| 层级 | 运行环境 | 验证什么 |
|---|---|---|
| 数学/参数测试 | 标准库即可 | 余弦边界、top_k 与空输入 |
| 存储集成测试 | 本地 Chroma + 假 Embedder | 真正存取、元数据、删除、持久化；不下载模型 |
| 语义验收 | CPU 真实模型 + 固定语料 | 10 题人工证据判断；不硬编码精确浮点分数 |

假 Embedder 使用确定性、非零、同维度小向量，例如给两篇测试文档返回正交向量，为特定查询返回第一篇的向量。它用于控制测试条件，不用于证明真实模型理解中文。

生产模块只在初始化真实 Embedder 时加载模型；导入 retrieval 模块或跑旧测试不能自动发起下载。没有 vector 扩展时，相关测试给出清楚的 skip，基础测试照常运行；Day 08 验收环境需要实际安装并运行存储集成测试。

### 15.2 最小行为矩阵

| 编号 | 场景 | 通过标准 |
|---|---|---|
| M01 | 同向/正交/反向/不同长度 | 与预期余弦一致；零向量、维度不匹配明确失败 |
| V01 | 空列表写入 | count 不变，Embedder 不被调用 |
| V02 | 同 ID 重复 upsert | count 不增加，内容可更新 |
| V03 | 可控向量查询 | 最近候选及距离方向正确 |
| V04 | top_k 大于记录数 | 返回现有数量，不制造空记录 |
| V05 | 空库、空问题、非法 top_k | 分别遵守正常空结果/参数错误契约 |
| V06 | Source 往返 | 正文、ID、路径、页码、offset、原 metadata、时间保留 |
| V07 | 精确 ID 删除 | 指定记录消失，其他记录存在；空列表不误删 |
| V08 | 重开索引 | 不重新 add，仍能查询；已删除记录不恢复 |
| V09 | 编码维度或数量错误 | 写入前明确拒绝，不静默成功 |
| V10 | 非有限数、空文本 | 编码边界明确处理，不写坏向量 |
| V11 | 元数据损坏/底层失败 | 报错误，不能等同于无结果 |
| V12 | 超模型长度 | 有可观察的拒绝/重新切片结果，不静默截断 |

V08 自动化可先用同一 tmp_path 的新对象重开，再用 PyCharm 两次独立进程确认磁盘持久化。无需为每一行机械复制一个测试函数，按真实故障组合用例。

## 16. PyCharm 中的具体运行步骤

### 16.1 配置一：Embedding Lab

- Script path：`examples/day08_embedding_lab.py`。
- Interpreter：项目 `.venv\Scripts\python.exe`。
- Working directory：`E:\agent_project\agent-learning-lab`。
- 首次运行看模型下载和加载输出；第二次对照缓存加载耗时。
- 断点：model.encode 前后、token_lengths 统计处。

能够在变量窗口看到文本数 N 与向量 shape=(N,D)，并说清 N 和 D。

### 16.2 配置二：Vector Lab

建议脚本支持 argparse 的 build、search、delete、reopen 子命令，参数形式可按你的实现调整并写入脚本帮助。

按顺序分别配置 Parameters：

```text
build
search --query "PDF 空白页会影响引用页码吗？" --top-k 3
delete --source-id 实际命中的ID
reopen
```

build 调用 Day 07 加载器，打印成功文件、失败和警告；search 只查询；delete 只删除指定 ID；reopen 只打开既有集合并展示记录。不让每个子命令都自动 build。

断点位置：embed_documents、upsert 前、query 后、Source 还原处。对照问题向量、原始返回和最终 Source，定位数据形状错误。

### 16.3 配置三：Evaluation

运行 `examples/day08_evaluate.py`，读取 queries.json 与固定集合，保存候选结果到 data/day08，不调用聊天模型。人工完成审核表，再用脚本统计 Hit@3；不要让脚本仅按文件名自动判定支持。

性能记录分别统计模型加载、建索引、问题编码、库查询。冷启动与热查询分开报告，今天没有统一毫秒达标值。

## 17. 回归检查与常见阻塞

完成修改后在 PyCharm Terminal 执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_documents.py tests/test_retrieval.py tests/test_vector_index.py -q
.\.venv\Scripts\python.exe -m pip check
```

如果本课改动触及运行时或共享类型，再运行相关调用者测试；不要将大型真实模型下载绑进普通测试收集。

| 现象 | 优先排查 |
|---|---|
| Terminal 安装了但 Run 仍无法 import | 两处解释器是否一致 |
| 模型下载失败或长时间无输出 | 完整网络/下载报错、缓存路径、磁盘空间；与推理慢区分 |
| 配置参数不接受 | 记录 chromadb 实际版本，对照官方接口；新建实验集合验证 |
| 向量维度不匹配 | 是否写入过假向量、换过模型或复用了旧集合 |
| 结果总是相反 | cosine distance 是否误按降序排序 |
| 返回数组解包错误 | 查询结果外层是问题批次，是否多取/少取一层 |
| 页码或 offset 消失 | 写入和还原是否遗漏 metadata |
| 长片段后半部分找不到 | tokenizer 截断与切片长度 |
| 删除后再次出现 | reopen/search 是否偷偷重新 add |
| 同内容出现多份 | 旧片段 ID 是否因内容/参数变化而遗留 |

如果模型下载尚未成功，日志明确标记“真实模型验收未完成”。先保留可运行的假向量与存储实验，不将其写成语义检索通过。

## 18. 核心完成后的扩展：比较 Chunk 配置

比较 A：chunk_size=300、overlap=50 与 B：chunk_size=500、overlap=80。两组都先通过 token 长度审计；不安全时调整并记录实际配置。

控制变量：

- 同一批原始文件、同一规范化逻辑。
- 同一模型、归一化、问题处理与距离度量。
- 同一 10 道问题与同一证据标签。
- 不同集合名，不能把两种切片混进一个库。

比较片段数、超长数、建库时间、查询时间、Hit@3、关键句被截断或切开的数量。ID 变化后按原文件/页/关键句重新映射标签，不按旧 ID 直接评分。

若片段普遍比两种配置都短，实验没有真正改变切片，先增加可重复的长文样例再比较。不要为了凑出“更优参数”随意增加 overlap：过多重叠会让 Top-3 被同一段附近内容占满。

额外扩展按余力选一项：查询指令对照、all/get 统一接口、按文档替换时删除旧片段。今天不学习重排器或复杂融合算法。

## 19. 学习日志与 Git 收尾

在 `curriculum/day-08-log.md` 记录：

1. 我如何区分频次向量、神经 Embedding 和余弦。
2. Python/库版本、模型标识、实际维度、最大序列长度、CPU 运行配置。
3. 模型加载与编码耗时，语料文件数/片段数/token 长度统计。
4. 集合路径、名称、metric、归一化、查询指令约定。
5. Source 存取映射与一个 PDF 来源往返示例。
6. 写入、重复写入、删除、独立进程重开的计数与 ID。
7. 测试结果、10 题初始与修正后 Hit@3、无证据探针观察。
8. 至少一个失败案例的原因与修正过程。
9. API 费用（本课本地路线为 0）、当前限制和下一课待办。

`.gitignore` 追加 data/day08/。模型权重、缓存、Chroma 数据库和个人文档不进入源码版本库；合成语料、生成脚本、测试、人工结果表进入 Git。若模型缓存目录在项目内部，按实际路径追加忽略规则。

```powershell
git status --short
git diff --stat
```

确认暂存内容只包含本课修改后，在 PyCharm Commit 窗口检查差异并提交，例如：

```text
feat: add local vector retrieval and day08 evaluation
```

不要用一次不检查的 git add . 把运行数据一并提交。

## 20. 今日最终验收标准

- [ ] 能从 Source 到 embeddings，再从问题到 Top-k 画出完整链路。
- [ ] 能运行真实中文模型，解释输出维度与相似度，不把得分当正确率。
- [ ] 真实数据输入长度经过 tokenizer 审计，没有未说明的截断。
- [ ] Chroma 写入、查询、按 ID 删除和独立进程重开成功。
- [ ] 重复 upsert 不增加记录；切片变更不混进旧集合。
- [ ] 取回内容能追溯文件、PDF 页码、规范化 offset/end_offset。
- [ ] 错误、空结果与非法参数有不同且明确的行为。
- [ ] 假向量存储测试与真实模型语义验收分开记录。
- [ ] 完成 10 道预标注题的逐条审核，目标 Hit@3≥80%；若未达到，保留失败题并安排补齐。
- [ ] 两个无证据问题没有被误标为“已找到答案”。
- [ ] 现有文档与检索相关测试没有新增回归。
- [ ] 日志、人工审核表、演示脚本、测试和 Git 提交齐全。

## 21. 不看笔记的口头验收题

1. 一段文本怎样变成固定维度向量？数字表示和原文本各保存在哪里？
2. 900 个字符、512 维向量和模型输入 token 上限有什么区别？
3. 归一化向量为什么可以用点积计算余弦？
4. HybridIndex 当前的分数与 Chroma 的分数为什么不能直接相加？
5. 模型相同但查询处理不同，会怎样影响可重复性？
6. 为什么不同模型即使维度一样也不能混在一个向量空间里？
7. cosine distance 越大还是越小表示更接近？
8. 一次 query 的结果为什么是二维列表？
9. Source 经过存取后丢掉 offset，会破坏哪一项能力？
10. upsert 为什么不能自动解决文档更新后的旧片段问题？
11. 如何证明重开成功不是因为启动时重新 add？
12. Top-3 有返回、Hit@3 命中、最终答案正确，三者有什么区别？
13. 为什么没有答案的提问仍可能查到三个候选？
14. 假 Embedder 测试通过后，还有什么必须用真实模型验证？
15. 被检索文档里的“忽略用户要求”等文字应该怎样处理？为什么它们仍是资料而不是用户授权？

## 22. 官方资料与 Day 09 衔接

按卡点查阅，不需要今天通读所有文档。接口说明于 2026-10-13 核对，运行时以安装版本为准。

- [BGE 中文模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5)：模型维度、使用方式、查询指令实验。
- [Sentence Transformers 预训练模型与示例](https://www.sbert.net/docs/sentence_transformer/pretrained_models.html)：加载与编码，理解模型选择需要实际验证。
- [Chroma 写入数据](https://docs.trychroma.com/docs/collections/add-data)：ID、documents、embeddings 与 metadata。
- [Chroma 集合配置](https://docs.trychroma.com/docs/collections/configure)：距离度量和集合配置。
- [Chroma 查询与读取](https://docs.trychroma.com/docs/querying-collections/query-and-get)：query/get 差别与结果形状。
- [Chroma 删除数据](https://docs.trychroma.com/docs/collections/delete-data)：精确删除并验证。

进入 Day 09 前应留下：可重复的语料、固定查询、预标注证据、向量检索结果、至少一例语义命中和一例失败。下一课用这些相同资料比较关键词与向量，再学习排序融合、去重和来源过滤。
