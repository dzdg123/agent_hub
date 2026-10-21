# Day 09 阶段五：去重诊断与证据出处

## 已实现的行为

1. 同一路重复 source_id：沿用融合层首次保留、去重后连续排名的约定，重复条目不额外贡献。
2. 两路同 source_id：最终输出一个 Source，保留各分支原始分数、排名和贡献。
3. 不同 ID 正文相同：只记录重复组，仍分别参与排序；不按正文或 file_path 删除记录。
4. 相邻片段有交叠：只记录经正文核对的重叠区间，不拼接正文，不改变 offset 或页码。
5. 规范 Source 与原始候选在分析、融合前后保持一致；返回结果及其嵌套 metadata 独立。

最终 Top-k 仍按融合分数截断，因此“保留不同出处”表示不因正文或路径相同而额外删除，不保证所有候选都能进入 Top-k。

## 代码入口

新增 src/research_agent/evidence_diagnostics.py。

### analyze_id_duplicates(branches)

输入为 dict[str, list[Source]]，读取每路原始列表，返回 IdDedupDiagnostics。此函数只计数，不执行去重或来源冲突检查；真正的冲突检查和 ID 去重仍在 fusion._prepare() 中。

示例关键词 A/A/B/C，向量 B/D/A：

| 字段 | 示例 | 定义 |
|---|---|---|
| raw_count_by_branch | keyword=4，vector=3 | 每路原始条目数 |
| unique_count_by_branch | keyword=3，vector=3 | 每路唯一 ID 数 |
| removed_count_by_branch | keyword=1，vector=0 | 同路额外重复出现次数 |
| shared_source_ids | A、B | 出现在两个或更多分支的 ID，每路只计一次 |
| unique_source_count | 4 | 全部分支 ID 并集大小 |
| raw_candidate_count | 7 | 原始条目总数 |
| within_branch_duplicate_count | 1 | 同路额外重复总次数 |
| across_branch_extra_count | 2 | 每路去重后条目总数减跨路唯一数 |
| repeated_candidate_rate | 3/7 | (原始条目总数 - 跨路唯一数) / 原始条目总数，空输入为 0 |

跨路共享 ID 是有用的多路命中信号，不应简单追求重复率越低越好。

### analyze_content_redundancy(canonical_sources, *, selected_ids=None)

输入完整规范清单，以及可选的统计范围 ID。None 表示全清单，空集合表示空范围，未知 ID 或重复的规范 ID 明确报错。

返回 ContentRedundancyDiagnostics：

| 字段 | 定义 |
|---|---|
| scope | canonical_corpus / selected_unique_sources；融合层标记 unique_candidates_before_top_k |
| selected_source_ids、source_count | 本次分析的唯一 ID 和数量 |
| duplicate_content_groups | 正文逐字符完全一致的不同 ID 分组，附各自 locations |
| duplicate_content_group_count | 重复正文组数 |
| duplicate_content_extra_count | 各组的 (ID 数 - 1) 之和；不是两两组合数 |
| adjacent_pairs_checked | 已核对的同坐标空间、连续 chunk_index 片段对数，含无重叠的片段对 |
| overlapping_adjacent_pair_count | 正文核对一致的相邻重叠对数 |
| overlap_pairs | 各对来源 ID、文件、页码、坐标基准、重叠起止和字符数 |
| coordinate_issues | 无法判断或坐标矛盾的来源 ID 与原因 |
| overlap_check_complete | 本次选中范围没有坐标问题；不表示检查了所有非相邻组合或其他未选中来源 |

正文按原始完整字符串分组，不改变大小写、空白、标点或 Unicode 字符。一个 ID 跨路命中多次只计一个来源，不会被当成不同出处的重复正文。

DuplicateContentGroup.locations 包含 EvidenceLocation：source_id、title、file_path、page、url、offset、end_offset、offset_basis、chunk_index。缺失或类型不合约的坐标显示为 None，具体问题见 coordinate_issues。

## 相邻与重叠的判定

1. 以 file_path、page、offset_basis 确定坐标空间，不跨文件或跨 PDF 页比较。
2. 接受当前加载器的 normalized_document_text / normalized_page_text；页级坐标必须带有效物理页码。
3. offset、end_offset、chunk_index 必须是非负整数，拒绝 bool；end_offset - offset 必须等于正文字符数。
4. 完整规范清单中 chunk_index 连续的两个片段才视为相邻，且双方都在选中范围内。不能因候选遗漏中间片段就把两端误当相邻。
5. 重复 chunk_index 会记录 ambiguous_chunk_index，不能猜测顺序。
6. 使用半开区间：start=max(两起点)，end=min(两终点)；end<=start 表示不重叠。
7. 正重叠还要核对两份正文中的对应子串。不同则记录 overlap_text_mismatch，不计入已验证重叠。

例如 A=[0,6) 的 abcdef 与 B=[4,10) 的 efghij，重叠区间为 [4,6)，正文均为 ef，重叠 2 个 Python 字符。

缺少坐标记录 missing_coordinates，坐标与正文长度不符记录 coordinate_content_length_mismatch，其他问题也各有明确 reason。统计报告问题，不修复或覆盖原字段，不影响融合排序。

## 融合层接入

FusionResult 追加了两个兼容字段：

```python
result.id_dedup_diagnostics
result.content_redundancy_diagnostics
```

fuse_rrf()、fuse_min_max() 自动填充。ID 统计基于输入原始候选；内容统计基于融合前跨路唯一候选，scope 明确为 unique_candidates_before_top_k。

TwoBranchRetriever.search() 的结果中，通过 result.fusion 读取；现有实验输出的 JSON 会自动保存两个字段：

```python
result = retriever.search("offset", candidate_k=6, top_k=3)
print(result.fusion.id_dedup_diagnostics)
print(result.fusion.content_redundancy_diagnostics)
```

如果单独分析最终 Top-k：

```python
from research_agent.evidence_diagnostics import analyze_content_redundancy

final_stats = analyze_content_redundancy(
    sources,
    selected_ids={source.source_id for source in result.final_sources},
)
```

merge_ranked() 保留 list[Source] 接口；分支贡献仍在每条 Source.metadata['_retrieval']['branches'] 中。需要完整统计时使用 fuse_rrf 或协调器的 search。

## 内部辅助函数

| 函数 | 用途 |
|---|---|
| _nonnegative_int(value) | 校验坐标整数，排除 bool |
| _location(source) | 生成不共享可变 metadata 的独立来源位置记录 |
| _coordinate_error(source) | 验证文件、区间、正文长度、切片序号和页级坐标契约，返回问题原因或 None |

## 实验入口

新增 examples/day09_dedup.py，make_demo() 提供固定来源与两路候选，main() 运行 RRF、验证输入不变、打印诊断并保存 JSON。

在项目根目录运行，无需 Embedding 模型：

```powershell
.\.venv\Scripts\python.exe examples/day09_dedup.py
```

固定案例包含：A 与 B 是 guide.pdf 第 1 页相邻片段，重叠 2 字符；C 是该文件第 2 页，D 是另一个文件第 9 页；A/C/D 正文相同。

关键词 A/A/B/C，向量 B/D/A，默认 top_k=4。预期输出 B/A/D/C，7 个原始条目、4 个唯一 ID、同路删除 1 次重复、共享 A/B、一组重复正文（额外 2 个来源）、一对相邻重叠，输入不变。

可重放已保存真实候选，不重新运行模型：

```powershell
.\.venv\Scripts\python.exe examples/day09_dedup.py --candidates-json data/day09/candidates/f0bb67e67041403db9ae861fe0070a4c/candidates.json
```

结果写入 data/day09/dedup/<run-id>/dedup.json，保留原候选快照、最终证据、完整轨迹和诊断。

本阶段没有合并不同 ID 的内容，因此不引入 alternate_sources；原始出处继续由各自 Source 和重复组的位置记录保存。
