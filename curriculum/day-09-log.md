# Day 09 学习日志：两路检索、RRF、证据上下文与公平评测

整理日期：2026-10-21。本文回顾本轮 Day 09 的代码、对话、实验与测试，方便以后快速恢复上下文。
学习日编号不代表全部工作在一个自然日完成。实现由 AI 协助补齐，知识是否能独立运用，仍可用文末复习问题检查。

## 这一天到底在做什么

Day 08 主要解决“把资料变成向量并检索”。Day 09 把检索扩展成一条有明确规则、可解释、可测试的证据处理流程：

```text
加载器提供同一份规范 Source（内容、ID、文件、页码、坐标）
    ↓
问题 + 文件类型/文件集合限制 → 统一 allowed_ids
    ↓
关键词检索最多 candidate_k 条     真实向量检索最多 candidate_k 条
    ↓                              ↓
分支状态、原始分数、排名、耗时、错误诊断
    └─────────────┬────────────────┘
                  ↓
每路精确 ID 去重 → RRF 累加贡献 → 最终 Top-k
                  ↓
按字符预算装入完整证据块，记录入选与遗漏原因
                  ↓
向后续回答模块提供带来源边界的资料
```

本轮完成的是检索与上下文准备链路，没有新增 DeepSeek 回答生成或回答正确性评测。

## 一、从原混合公式里拆出关键词检索

原 HybridIndex 的公式是：

```text
score = 0.7 × 词项频次余弦 + 0.3 × 字符频次余弦
```

这两项使用不同的计数单位。词项分支先 tokenize()，再 Counter；字符分支直接按字符计数。
字符分支可能因为共同汉字、标点等获得相似度，原混合分数不能直接称为纯关键词分数。

独立 KeywordIndex 使用：

```python
query_counter = Counter(tokenize(query))
document_counter = Counter(tokenize(source.content))
score = _cosine(query_counter, document_counter)
```

需要记住的数学含义：

```text
cosine(q, d) = Σ(q词项次数 × d同词项次数) / (q的范数 × d的范数)
```

只有共有词项才贡献分子。它既看出现次数，也用向量范数缩放，不是简单数命中多少个词。
当前实现没有 BM25 的 IDF 和文档长度校正机制，不能贴 BM25 标签。

### tokenize 的实际输出

整理日志时再次运行 day09_hybrid_lab.py，得到：

```text
offset         → ['offset']
max_steps add set → ['max_steps', 'add', 'set']
MODEL_NAME     → ['model_name']
model-name     → ['model', 'name']
最大步骤数     → ['最大', '大步', '步骤', '骤数']
最大步数是多少？ → ['最大', '大步', '步数', '数是', '是多', '多少', '少？']
```

英文、数字和下划线由正则提取并转小写；连字符会拆开英文词项。
中文是相邻字符片段，当前规则甚至可生成“少？”这样的片段，不能等同完整中文分词。
以后解释大小写、特殊符号或中文边界时，应先看实际 tokenize 输出。

### 两个索引怎样理解

KeywordIndex 和 ChromaIndex 都是对同一份 Source 的检索索引。
前者比较显式词项计数，后者存储并比较 Embedding 模型生成的稠密向量。
从数学上看词项计数也可以表示为向量，所以更准确的区别是“词项频次表示”和“学习得到的稠密表示”。

KeywordIndex 的契约包括空白问题返回 []、拒绝非法 top_k（含 bool）、不补零分候选、同分按 source_id 排序，
以及深复制输出，避免嵌套 metadata 被调用方修改后污染原始资料。

## 二、两路检索必须使用同一套来源和参数含义

新增 TwoBranchRetriever，把两路放进共同契约：读取同一份规范 Source，保留相同 ID，验证来源一致性。
不能为另一分支重新编号，也不能把某路查到的正文悄悄覆盖规范资料。

三个数量控制的是不同阶段：

| 参数 | 控制范围 | 本轮常用值 |
| --- | --- | --- |
| candidate_k | 每个分支最多提供的候选数 | 6 |
| top_k | 融合后最多保留的 Source 数量 | 3 |
| max_context_chars | 这些片段真正装入上下文的字符容量 | 2000 |

candidate_k 至少不小于 top_k，并被允许范围内的记录数限制。
“每路最多6条”不表示强行凑够6条；关键词实际命中1条就只返回1条。
两路当前串行运行；同步关键词计算和本地 Embedding 不会因为包上 async 自动获得并发收益。

Source 列表传递证据，诊断对象记录分支状态、候选数、耗时和失败原因。
原始 score、metric、rank 和融合贡献保留在轨迹里，便于解释每条结果怎么来的。

## 三、理解 min-max 和 RRF 各自在做什么

关键词余弦与向量余弦的分数分布不同。两路都出现0.8，不代表具有相同相关性或可信程度。

min-max 是每路候选内部的分数缩放：

```text
normalized = (score - 最低分) / (最高分 - 最低分)
combined = 0.5 × keyword_normalized + 0.5 × vector_normalized
```

缺席某路贡献0。单候选或同一路全部同分时，分别试过统一赋1和统一赋0的教学策略。
负 score 可以正常归一化；如果原始返回的是距离，要先转成越大越好的 score，不能在融合时重复转换。
Chroma cosine 距离在当前适配器中通过 score=1-distance 转换。

两个限制尤其重要：扩大 candidate_k 可能改变极值，导致原候选的归一化分数变化；
一个很差的单候选也可能被赋成1。因此归一化统一尺度，不等于校准证据可信度。

主线 RRF 使用排名，而不是把原始分数硬加在一起：

```text
rrf_score = Σ 1 / (60 + 该分支排名)
```

排名从1开始，未出现的分支贡献0。rank_constant=60与top_k=3无关。

手算案例：关键词 [A,B,C]，向量 [B,D,A]。

| ID | 关键词贡献 | 向量贡献 | 总分约值 |
| --- | --- | --- | --- |
| A | 1/61 | 1/63 | 0.03227 |
| B | 1/62 | 1/61 | 0.03252 |
| C | 1/63 | 0 | 0.01587 |
| D | 0 | 1/62 | 0.01613 |

排序 B、A、D、C。两路都靠前可累加优势，只有一路第一则只有该路贡献。
RRF 是本项目的主线排序方法；这不代表所有系统都必须选择它。RRF 分数也不是答案正确概率。

## 四、过滤必须发生在每路候选截断之前

如果全库前三都是 TXT，第4条才是用户需要的 PDF，先查前三再筛 PDF 会错过它。
本轮做法是先从规范 Source 生成 allowed_ids，再让两路只在允许范围内检索。

```text
None：不限制
set()：明确没有允许来源，返回空结果
多个条件：AND取交集
同一条件里的多个值：允许其中任意一个
未知过滤字段：明确拒绝
```

Chroma 写入顶层 filter_source_id，查询使用：

```python
where = {"filter_source_id": {"$in": sorted(allowed_ids)}}
```

file_type、relative_path 的语义先由规范 metadata 解析成允许 ID；本轮没有依赖 Chroma
读取 source_metadata_json 内部的嵌套字段，也没有要求必须新增 filter_file_type 等顶层字段。
新字段使用独立 Day09 集合，不假定 Day08 旧库已经自动回填。

测试确实使用真实 Chroma + 假 Embedder，检查 where、过滤范围内的 n_results 和真实返回值。
只测 Python 过滤函数不能证明数据库路径正确。

## 五、去重的对象是来源 ID，不能丢掉出处

| 情况 | 处理 |
| --- | --- |
| 同一路重复 ID | 保留首次出现项，再连续排名，不能重复贡献 |
| 跨路相同 ID | 一个最终 Source，累加两路贡献 |
| 不同 ID、相同正文 | 保留来源差异，另记重复正文诊断 |
| 同文件不同页 | 可同时保留，不能按 file_path 删除 |
| 同 ID 但正文或来源冲突 | 明确报错，不能让最后一个覆盖前一个 |

[A,A,B,C] 去重后应与 [A,B,C] 的融合排名、分数和贡献轨迹一致；原始重复数量的诊断当然不同。
输出从规范 Source 深复制，检索 score、rank、_retrieval 等运行时字段不参与正文来源冲突判断。
同时记录重复正文组与可验证的相邻片段重叠，不修改 offset，不把拼接文本伪装成原始片段。

Chroma 查询输出的 metadata['_retrieval'] 是运行时字段，不能将查询后的 Source 原样写回现有索引。
重建库要用加载器提供的规范 Source。

## 六、把 Top-3 变成受预算约束的上下文

用户对话中重点澄清了两个概念：

1. 预算限制的是最终 context.text 的 Python 字符数，必须满足 len(text)<=budget。
2. 一个完整证据块对应一个 Source，加上它的标题、文件、页码、坐标和边界标记。

一个 Source 通常只是原文件切分后的片段。“完整块”表示保留该片段全部正文，不表示把整份 PDF 放进去。

build_context 按融合排名依次尝试：整块放得下就放入，放不下则记录原因，继续尝试后面更短的块。
不截断半句、不 strip 正文、不重新计算原文 offset。标题、来源字段、分隔符、换行和外层说明也计入预算。

返回字段包括 text、included_source_ids、omitted_source_ids、used_chars、budget、omission_reasons、status。
状态区分 ok、partial、budget_exhausted 和 empty_input。预算要求正整数，bool也拒绝。

实际合成实验：

| 预算 | used_chars | 入选 |
| --- | --- | --- |
| 2000 | 1181 | offset、max_steps、model_name三段 |
| 444 | 444 | 后两段，跳过最长的第一段 |
| 194 | 194 | 最短的model_name段 |
| 1 | 0 | 无块可放入，budget_exhausted |

这个策略可能跳过最相关的长片段，不是最优装包算法。
included_source_ids 表示“已提供给模型”，不自动等于“答案实际引用了这些资料”。

Python字符数不是模型token数，BGE tokenizer也不能作为DeepSeek精确计数器。
后续还需计算系统提示、用户问题、其他消息和输出预留。
检索正文里的指令始终是待分析资料；边界说明有助于区分资料，但不能单靠分隔符保证防住提示注入。

## 七、失败、空结果与降级是三种不同情况

降级：一部分功能发生明确运行故障，显式允许后使用仍正常的另一分支，并说明结果来自不完整流程。
某路正常运行但没命中不算降级。两路都失败必须明确失败，不能显示成“没有资料”。

```python
result = retriever.search(
    "offset", candidate_k=6, top_k=3,
    allow_degraded=True, query_id="q-007",
)
```

allow_degraded 由调用方配置，默认 False；可以由实验脚本或应用后端决定，不必每次询问最终用户。

| 整体状态 | 含义 |
| --- | --- |
| ok | 两路执行成功，至少一路有结果 |
| empty | 两路执行成功，都无候选 |
| skipped | 空白问题或没有允许来源，未执行查询 |
| degraded | 一路失败、另一路成功，调用方允许降级 |
| failed | 不允许单路降级，或两路都失败 |

failed 的 final_sources/final_count/fusion 为 None；成功但无结果的 search 返回 []/0。
失败分支 candidate_count=None，正常空分支 candidate_count=0。
分支诊断包含问题ID关联、分支名、候选数、耗时、错误类型、错误消息及失败阶段。

协调层只捕获 RetrievalOperationalError。模型/数据库适配层在明确的运行边界转换已识别错误并保留 __cause__。
不能捕获所有RuntimeError，因为来源数据与配置异常也继承它；非法过滤、正文冲突和未分类程序错误仍抛出。
LazyCandidateIndex 将模型加载、打开索引等准备工作纳入请求诊断，否则构造阶段先失败就无法返回分支状态。

模拟超时使用故障注入：临时把 search 替换为抛专用异常的函数，之后恢复。
没有真的等待超时，error_type='TimeoutError'是诊断类型标记。它验证降级流程，不证明真实超时控制已经实现。
受控9案例实际得到ok=2、empty=1、failed=2、degraded=4，降级结果单独统计。

## 八、真实三组公平对比：观察到融合未必更好

主实验比较独立关键词、真实向量、RRF三组。每题两路只召回一次最多6条候选，
独立方法各截前三，RRF使用完整候选融合后截前三，三组分别按同一2000字符预算装包。
模型加载、建库、预热与热查询分开记录，不把RRF融合函数耗时冒充完整两路成本。

原Day08基线：12文件、13个Source、10道正向题和2道探针。
另存挑战v1：6道题，其中5道有允许证据、1道过滤后无证据。两组正向分母分别10和5。
没有答案的探针不能混入正向Hit@3分母；失败题不能被删除后缩小分母。

真实运行目录：`data/day09/comparison/20261021T063812Z-c0173b75`。
18题均完成、没有分支失败，检索和上下文过滤违规均为0。

| 自动辅助核对 | 关键词 | 向量 | RRF |
| --- | --- | --- | --- |
| 原10题的预标注ID命中 | 9/10 | 10/10 | 9/10 |
| 挑战正向5题的预标注ID命中 | 4/5 | 5/5 | 4/5 |

注意：这是预标注ID核对，不是已完成人工审核的正式Hit@3。
日志整理时review.csv仍有121条待审核记录；正式Hit@3、Top-1支持率、预算后命中率保持null。
不能因为目标ID命中就自动给正文支持等级2，也不能把未审核记录记作0。

### 一个实际的预标注证据排名退化案例

Q06：“PDF 中间有空白页，后续引用的页数该怎样记录？”
预标注必要证据位于document_tracking.pdf物理第3页。

| 方法 | 本次实际Top-3标题 |
| --- | --- |
| 关键词 | printed_pages.md → gardening.md → security.md |
| 向量 | printed_pages.md → PDF第1页 → PDF第3页 |
| RRF | printed_pages.md → PDF第1页 → security.md |

向量分支保留了目标页，RRF却将它挤出前三。C03的同类问题也出现相似现象。
这说明双路排名累加可能提升干扰片段，而非保证融合总优于单路。
这里的结论限于实际排名与固定证据ID，最终支持等级和不支持候选数仍待正文审核。
printed_pages.md讨论印刷页码，不能只因为共享“页码”词就当成PDF物理页引用规则。

对话中还有一次q-007输出，两路status均为ok，关键词1条、向量6条，最终上下文包含offset.md、security.md和PDF第1页。
它帮助区分“流程正常”与“每条结果都直接相关”：ok只说明运行状态，Top-3也可能混入不支持当前问题的片段。

### 审核与指标如何理解

每个问题对两路候选并集按source_id去重审核，等级0=无关/不支持，1=主题相关但缺关键证据，2=正文直接支持。
同一个候选在不同方法中共用一次审核，保留理由、审核者与人工抽查状态。

- Hit@3：正向题前三中至少有一条等级2。
- Top-1支持率：正向题首条是等级2。
- 上下文保留命中率：经过预算后included_source_ids仍包含等级2。
- 不支持候选数：Top-3的等级0数量，等级1另列。
- 候选重复率：融合前每题两路原始候选总数减唯一ID数，再除原始总数；空分母为0。

跨路重合本身是有用信号，重复率不能简单认为越低越好。
分数、来源匹配、正文支持、进入上下文、答案实际正确，是不同层次，不能互相替代。

## 九、关键行为测试与已有验证证据

K01～E02共17类验收已映射到测试，参数化展开56项。
涉及关键词、RRF手算/去重/冲突/深复制、min-max、过滤、不同页出处、字符预算和失败降级。
day09_case标记允许单独运行；该组测试禁止构造真实Embedding模型，模型误加载会立即失败。
真实Chroma路径使用固定二维假向量测试，不需要下载真实模型。

阶段实施中已实际执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m day09_case -q
```

结果：56 passed，412 deselected；两项真实Chroma过滤集成实际执行，无skip。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval.py tests/test_fusion.py `
  tests/test_source_filters.py tests/test_context.py tests/test_retrieval_failures.py `
  tests/test_evidence_diagnostics.py tests/test_hybrid_retrieval.py tests/test_comparison.py -q
```

结果：189 passed。存在Chroma旧Embedding配置接口的弃用警告，没有测试失败。
这些是Day09阶段九已执行记录，不沿用Day08的115 passed。本次新增日志未重新运行整组测试或真实三组实验。

## 十、以后从哪些文件和命令重新进入

以下路径相对项目根目录`E:\agent_project\agent-learning-lab`。

| 文件 | 用途/主要入口 |
| --- | --- |
| src/research_agent/retrieval.py | tokenize、KeywordIndex、ChromaIndex、兼容merge_ranked |
| src/research_agent/retrieval_pipeline.py | TwoBranchRetriever.search / retrieve_candidates、LazyCandidateIndex |
| src/research_agent/fusion.py | fuse_rrf、fuse_min_max与贡献轨迹 |
| src/research_agent/source_filters.py | normalize_filters、resolve_allowed_ids |
| src/research_agent/evidence_diagnostics.py | ID重复、重复正文、相邻重叠诊断 |
| src/research_agent/context.py | build_context、format_source_block、render_context |
| src/research_agent/retrieval_errors.py | 可降级错误及适配边界 |
| src/research_agent/comparison.py | 单题三组对比、审核表、指标、报告 |
| examples/day09_candidates.py | 实际两路候选/融合检索，支持PDF和文件过滤 |
| examples/day09_fusion.py | 手算案例、min-max对照、候选重放 |
| examples/day09_dedup.py | 证据去重及出处诊断演示 |
| examples/day09_context.py | 固定片段或保存候选的预算实验 |
| examples/day09_failures.py | 不加载模型的故障与降级演示 |
| examples/day09_compare.py | 真实三组对比run和审核后report |
| curriculum/day09-challenge-v1.jsonl | 独立挑战题版本 |

常用命令：

```powershell
# 真实检索并融合
.\.venv\Scripts\python.exe examples/day09_candidates.py `
  --query "怎样避免 Agent 一直调用工具？" --candidate-k 6 --top-k 3 --fuse

# 限制PDF
.\.venv\Scripts\python.exe examples/day09_candidates.py `
  --query "PDF 页码如何记录？" --file-type pdf --fuse

# 不加载模型的机制实验
.\.venv\Scripts\python.exe examples/day09_fusion.py --demo
.\.venv\Scripts\python.exe examples/day09_context.py
.\.venv\Scripts\python.exe examples/day09_failures.py

# 新一次真实三组实验，每次独立目录
.\.venv\Scripts\python.exe examples/day09_compare.py run

# 当前已有运行的审核后报告
.\.venv\Scripts\python.exe examples/day09_compare.py report `
  --run-dir data/day09/comparison/20261021T063812Z-c0173b75
```

## 十一、PyCharm流程与尚未完成的收尾

解释器：`E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe`。
工作目录：`E:\agent_project\agent-learning-lab`。
用上述实际入口建立Python配置，将命令中脚本名之后的参数填入Parameters。
断点顺序：允许集合 → 两路候选 → 单路ID去重 → RRF累加 → Top-k → 上下文装包。
停在断点行时通常尚未执行该行，按F8后再看变量变化；用F7进入函数。

本轮已经解释了配置步骤，但没有将“已保存PyCharm运行配置、全部断点独立复现”当成已完成验收。
当前day09_hybrid_lab.py仍只是tokenize演示，不支持教程建议的rrf-demo/search/context子命令。
day09_compare_retrieval.py不存在，实际用day09_compare.py；当前配置与上下文分别存于config.json和raw_results.json，
不能假定已有独立manifest.json/context_results.json。

还需完成或按需要补充：

- 填写真实实验的review.csv，只改support_level、reason、reviewer、human_checked，再生成正式指标。
- 根据正文审核分析关键词优势、向量优势及融合持平/退化；没有观察到的差异明确写未观察到。
- 独立运行断点链路，记录每个阶段输入/输出数量及变化原因。
- 若要求统一Hybrid Lab CLI，再实现统一入口；原始三列“纯关键词/纯字符/原混合”实验表也可另补完整记录。
- 复核Day09改动与其他日期的未提交改动，完成有明确范围的Git收尾；本轮未执行提交。

## 十二、以后复习时先问自己

1. 当前关键词分数怎么算？为什么不是BM25？为什么中文输出不等于中文分词？
2. 为什么两路都使用Source，却要区分规范对象与带运行时轨迹的查询结果？
3. candidate_k=6、top_k=3、2000字符预算分别在哪个阶段起作用？
4. 不看代码能否手算ABC与BDA，解释B为什么排第一？
5. 为什么None和空allowed_ids不同？为什么过滤必须在候选截断前？
6. 为什么同文件不同页不能按路径去重？输出深复制解决什么问题？
7. 某个Source放不下预算后，为什么还要继续尝试后面的片段？哪些字符也算容量？
8. empty、degraded、failed分别表示什么？allow_degraded能不能绕过正文冲突？
9. 临时替换search抛异常为什么叫故障注入，而不是真实超时控制？
10. 为什么预标注ID命中、正文等级2、上下文保留和答案正确率不能混为一谈？
11. 本次RRF在哪道题把向量分支保留的目标证据挤出了前三？
12. 为什么121条审核未完成时，正式指标必须保留null，而不是缩小分母？

以后能用实际代码和实验结果回答这些问题，才表示把Day09从“代码跑通”进一步变成了可以独立解释和修改的能力。
