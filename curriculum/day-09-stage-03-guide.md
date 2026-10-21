# Day 09 阶段三：代码与接口说明

## 完成的功能

- RRF 主线：同一路先按 ID 去重再连续排名，跨路累加贡献，最终 ID 唯一。
- min-max 对照：关键词和向量各占 0.5；同分分别试赋 1 和赋 0。
- 来源一致性：候选须与规范清单的正文、标题、路径、页码、URL、来源 metadata 一致。
- 保留轨迹：原始分数、指标、排名、距离、归一化分数和融合贡献可查看。
- 不修改输入：最终 Source 取自规范清单的深副本，嵌套 metadata 独立。
- 旧接口兼容：merge_ranked() 继续返回 list[Source]，内部复用新 RRF。

## 文件

| 文件 | 改动 |
|---|---|
| src/research_agent/fusion.py | 补全已有两个函数占位，增加共享校验、结果类型和贡献计算 |
| src/research_agent/retrieval.py | merge_ranked 改为 RRF 兼容入口 |
| src/research_agent/retrieval_pipeline.py | CandidateResult 增加 fusion；TwoBranchRetriever 增加 search |
| examples/day09_fusion.py | 手算案例、候选文件重放、两种同分策略和窗口变化实验 |
| tests/test_fusion.py | 融合数学、边界、深复制、CLI 输出与重放测试 |
| tests/test_hybrid_retrieval.py | 增加 search 的端到端结果与贡献验证 |

## 主要调用入口

### 1. fuse_rrf

```python
fuse_rrf(
    branches: dict[str, list[Source]], *,
    canonical_sources: list[Source],
    top_k: int = 3,
    rank_constant: int = 60,
) -> FusionResult
```

branches 示例：{"keyword": [...], "vector": [...]}。列表已有的顺序就是分支排名，不能根据原分数重新排序后再冒充原排名。

canonical_sources 是加载器输出的规范来源，不得带 metadata['_retrieval']。

先校验每条候选是否与规范来源一致，再按 ID 保留每路第一次出现。重复条目的来源冲突仍报错；同 ID 仅分数不同则保留第一次的分数。

去重后从 1 连续编号，每条贡献为 1 / (rank_constant + rank)。按总分降序，同分按 source_id 升序，最后取 top_k。

top_k 和 rank_constant 都要求正整数，拒绝 bool。空输入正常返回空结果。原始分数必须有限，但不参与 RRF 数值计算。

### 2. fuse_min_max

```python
fuse_min_max(
    branches: dict[str, list[Source]], *,
    canonical_sources: list[Source],
    top_k: int = 3,
    equal_score_value: float = 1.0,
) -> FusionResult
```

此教学版本只接受 keyword、vector 两个分支名；每路权重固定为 0.5。即使一路为空，另一条权重仍是 0.5，不自动改为 1。

共享 RRF 的候选校验和 ID 去重，随后在各分支去重后的候选上计算极值：

```text
normalized = (score - min_score) / (max_score - min_score)
contribution = 0.5 * normalized
```

单条与全部同分都采用 equal_score_value，只能选择数值 0 或 1，拒绝 bool。负分可正常归一化；归一化为零的候选仍保留。

使用 Source.score，当前 Chroma 已转换为 1 - distance，不能再次转换。

### 3. TwoBranchRetriever.search

```python
retriever.search(
    query: str, *,
    candidate_k: int = 6,
    top_k: int = 3,
    allowed_ids: set[str] | None = None,
    rank_constant: int = 60,
) -> CandidateResult
```

内部只召回一次两路候选，再调用 fuse_rrf。写入 result.fusion、final_sources、final_count，并给各路原轨迹的 fusion_contribution 填 RRF 贡献。

retrieve_candidates() 仍是仅召回入口，其 final_sources、final_count、fusion 保持 None。search() 已经融合，空结果则 final_sources=[]、final_count=0。

```python
result = retriever.search("offset", candidate_k=6, top_k=3)
for source in result.final_sources:
    print(source.source_id, source.score)
for trace in result.fusion.traces:
    print(trace.branch, trace.rank, trace.contribution)
```

### 4. merge_ranked

```python
merge_ranked(
    result_sets: list[list[Source]],
    top_k: int = 10, *,
    rank_constant: int = 60,
    canonical_sources: list[Source] | None = None,
) -> list[Source]
```

原有 merge_ranked([first, second], top_k=3) 调用保持有效。新增的两个参数都只能按名称传入。

提供规范清单时以清单为准；未提供时，从每个 ID 首次出现的 Source 建立临时基准，随后仍校验全部候选，绝不让后出现的正文覆盖早先正文。

分支名自动设为 branch_0、branch_1 等。返回列表中的 Source.metadata['_retrieval']['branches'] 保存各分支贡献；需要独立 FusionResult 时直接调用 fuse_rrf。

## 返回结构

### FusionTrace

| 字段 | 含义 |
|---|---|
| source_id | 来源 ID |
| branch | 分支名 |
| raw_score | 分支原始 Source.score |
| metric | token_count_cosine / embedding_cosine；通用分支读取原 metric 或标为 branch_score |
| rank | 分支去重后的连续排名，从 1 开始 |
| normalized_score | min-max 的归一化值；RRF 为 None |
| contribution | 此分支实际加入总分的贡献 |
| distance | 可用时保留原向量距离 |

### FusionResult

| 字段 | 含义 |
|---|---|
| method | rrf 或 min_max |
| sources | 最终 Top-k 的规范 Source 深副本，score 为融合总分 |
| traces | 所有去重候选的贡献，包括未进入最终 Top-k 的来源 |
| unique_candidate_count | 融合前跨路唯一候选 ID 数量 |
| final_count | 实际最终数量 |
| parameters | rank_constant，或两路权重及同分策略 |

最终 Source 还附有 metadata['_retrieval']，包含 method、metric、parameters 和该来源各分支轨迹。修改它不污染输入或独立 traces。

这些仍是查询结果，不能直接写回当前 ChromaIndex。重建数据库继续用规范 Source。

## fusion.py 内部函数

| 函数入口 | 作用 |
|---|---|
| _positive_int(value, name) | 校验正整数参数，错误信息包含参数名 |
| _identity(source) | 提取来源身份用于比较；忽略 score、fetched_at、metadata['_retrieval'] |
| _prepare(branches, canonical_sources) | 验证规范清单、分数、来源冲突、运行时字段类型，再逐路去重；返回分支副本和规范 ID 映射 |
| _trace(hit, branch, rank, contribution, normalized_score=None) | 生成一条分支贡献记录，保留原指标和向量距离 |
| _finish(method, canonical, traces, top_k, parameters, id_diagnostics) | 汇总贡献、稳定排序、深复制最终来源并附轨迹，返回 FusionResult；阶段五另附 ID 与内容冗余诊断 |

## 实验脚本的函数

| 函数入口 | 作用 |
|---|---|
| make_demo() | 返回规范 A/B/C/D 和关键词 ABC、向量 BDA 固定候选 |
| load_saved_candidates(path, dataset) | 读取阶段二候选；真实数据重新校验固定资料和 fingerprint；受控案例使用固定演示资料 |
| compare_fusions(branches, canonical_sources, *, top_k=3, rank_constant=60) | 同一份候选跑 RRF、同分赋 1 的 min-max、同分赋 0 的 min-max；返回三个独立结果 |
| normalization_examples() | 返回单候选策略及 candidate_k 窗口改变的固定实验 |
| normalization_examples 内部 hit(name, score) | 从合成规范对象复制出指定分数的候选，只供固定实验使用 |
| main() | 解析命令行参数，运行比较，保存完整 JSON 并打印排名摘要 |

## 在 PyCharm Terminal 运行

Working directory 使用项目根目录 E:\agent_project\agent-learning-lab。

固定手算，展示四条：

```powershell
.\.venv\Scripts\python.exe examples/day09_fusion.py --demo --top-k 4
```

RRF 应输出 B、A、D、C，对应约 0.032522、0.032266、0.016129、0.015873。

重放已保存的真实候选，避免重新召回导致输入变化：

```powershell
.\.venv\Scripts\python.exe examples/day09_fusion.py --candidates-json data/day09/candidates/ec2e955bf62d4c9e89b11aa2a76bb718/candidates.json
```

新结果写入 data/day09/fusion/<run-id>/fusion.json；不会修改原 candidates.json。JSON 保存输入候选快照、三个结果、全部贡献和固定归一化实验。

## 实验结论的边界

1. offset 实验中关键词仅一条，原分数约 0.2121。同分赋 1 后它贡献 0.5；赋 0 后贡献 0。两者均为教学约定。
2. 固定窗口例子：向量分数 A=0.9、B=0.8、C=0.1。只取 A/B 时 B 归一化为 0，取 A/B/C 时 B 变为 0.875。原分数没变，候选极值变了。
3. 固定低分单候选例子中，A 的原分数仅 0.001，仍可能被赋 1。与另一分支叠加后，同分策略会改变第一名。
4. 本次真实 offset 候选在 RRF、两种 min-max 下 Top-3 顺序相同；同分策略改变分数，没有改变该问题排名。不能据此认为三种方法普遍等价。
5. RRF 与归一化都只产生排序量，不表示答案正确概率。本阶段不实现上下文预算或失败降级。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_fusion.py tests/test_retrieval.py tests/test_hybrid_retrieval.py tests/test_chroma_index.py tests/test_vector_index.py tests/test_workflow.py -q
```
