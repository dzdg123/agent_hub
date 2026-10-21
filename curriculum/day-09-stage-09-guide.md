# Day 09 阶段九：K01～E02关键行为验收

全部17个场景复用现有测试并补强断言，通过`day09_case`标记单独选择。
参数化展开后共56项；真实语义效果仍由day09_compare.py独立实验，不在数学测试中加载模型。
本阶段没有修改检索、融合或上下文的生产实现。

## 运行入口

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m day09_case -q
```

查看每个测试名称或只收集不执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m day09_case -v
.\.venv\Scripts\python.exe -m pytest -m day09_case --collect-only -q
```

标记在pyproject.toml注册；tests/conftest.py针对带标记的测试自动禁止
SentenceTransformerEmbedder构造。若未来误将真实模型加载加入验收，测试会立即失败，
不依赖本机是否缓存模型，也不触发模型下载。
该限制只作用于关键验收，不影响其他专门验证Embedding适配器的测试。

Chroma集成测试使用临时目录与直接返回固定二维向量的Embedder，embedding_function=None，
不会调用Chroma默认的Embedding模型。需要安装项目的vector依赖；缺失Chroma时相关测试会显示skip，
不能将此情况说成数据库路径已验收。本次环境两项集成都实际执行通过，没有跳过。

## 编号与测试映射

| 编号 | 测试文件 | 主要函数与验收 |
| --- | --- | --- |
| K01 | test_retrieval.py | test_keyword_search_finds_exact_term / does_not_return_zero_score_results / returns_empty_for_blank_query：精确命中、无交集与空问题 |
| F01 | test_fusion.py | test_rrf_matches_hand_calculation_and_keeps_omitted_candidate_traces：ABC与BDA排序BADC，各项得分与手算一致 |
| F02 | test_fusion.py | test_duplicate_is_removed_before_continuous_rank_and_only_contributes_once：AABC与ABC的来源、轨迹、连续排名一致；兼容merge_ranked |
| F03 | test_fusion.py | test_shared_id_is_one_source_with_two_independent_branch_contributions：单ID仅一条输出，keyword/vector各贡献1/61，总分2/61；轨迹完整 |
| F04 | test_fusion.py | test_ties_use_source_id_and_rrf_uses_rank_not_raw_score / test_empty_branches：同分按ID排序、空分支和全空安全返回 |
| F05 | test_fusion.py | test_conflict_including_duplicate_entry_is_not_hidden：正文、标题、文件、页、URL及关键metadata冲突明确报错 |
| F06 | test_fusion.py | test_runtime_fields_are_ignored_inputs_not_modified_and_outputs_are_deep_copies：修改结果的嵌套metadata与贡献轨迹，不污染规范来源、候选、另一次融合结果或独立trace |
| N01 | test_fusion.py | test_empty_branches / test_singleton_and_all_equal_policy / test_min_max_negative_scores_missing_branch_and_zero_candidates_retained：空、单项、同分赋0/1、负分，避免除零且不重复转换distance |
| S01 | test_retrieval.py、test_source_filters.py | test_keyword_search_distinguishes_none_and_empty_allowed_ids；test_real_chroma_none_is_unrestricted_but_empty_ids_do_not_query_or_embed：None不限制，空集合不查询/不编码 |
| S02 | test_source_filters.py | test_real_chroma_filter_before_candidate_cutoff_and_final_rrf：两路全库前三TXT，第4条PDF；先过滤后两路、RRF与上下文仅PDF |
| S03 | test_source_filters.py | test_invalid_filters_are_rejected_even_for_empty_query / test_resolver_none_empty_or_and_and_multiple_chunks，以及S02中的不存在文件：非法字段拒绝，无匹配不发出不受限查询 |
| D01 | test_evidence_diagnostics.py | test_distinct_ids_with_identical_content_and_different_pages_are_retained：RRF与min-max均保留同文件不同页、异文件同正文的来源 |
| C01 | test_context.py | test_exact_budget_includes_headers_wrapper_and_separators：包括外壳、分隔符与换行，预算恰好/差一字符边界 |
| C02 | test_context.py | test_skip_long_top_hit_and_continue_in_rank_order / test_remaining_budget_skip_still_tries_later_short_block：跳过长块，继续放入后续短块，原因与增量预算准确 |
| C03 | test_context.py | test_empty_and_exhausted_have_no_wrapper / test_invalid_budget_rejected_even_with_empty_input：空输入、全部放不下及非法预算明确区分 |
| E01 | test_retrieval_failures.py | test_degraded_result_keeps_intersection_of_filters_and_explicit_allowed_ids：双向模拟单路超时，保留AND过滤及显式ID交集，诊断完整，上下文也不越界 |
| E02 | test_retrieval_failures.py | test_default_strict_and_both_failed_even_when_degradation_allowed / test_empty_is_success_and_is_distinct_from_failure：两路失败为None，无结果为[]/0，状态、异常与fusion不同 |

## 此次补强内容

- F03新增集中证明：一条来源、两路贡献、分数之和及序列化轨迹一致。
- F06新增另一次融合结果快照，证明嵌套metadata之间没有共享引用污染。
- S01新增真实Chroma查询，None调用数据库，空集合不调用query或embed_query。
- S02增加两路第4名精确断言、真实文件/物理页上下文，以及无匹配时数据库调用数量不增加。
- E01新增关键词故障和向量故障两个方向，在file_type、指定文件、allowed_ids交集下验证降级不扩大范围。
- E02补齐candidate_count=None与0、final_sources=None与[]、fusion=None与已完成空融合等断言。

S02的查询捕获只记录参数，随后仍调用原始collection.query，数据库真实执行。
测试检查`where={"filter_source_id":{"$in":["doc-3","doc-4"]}}`与`n_results=2`。
如果忽略where后先查全库前两条，会取到TXT，测试不能通过；没有用Python谓词冒充数据库过滤。

E01用专用RetrievalOperationalError模拟预期超时，不真正等待；仍经过协调器的来源校验、
允许范围计算、状态决策、RRF和上下文构建。降级最终只有pdf-2，分数为单路1/61。

## 相关回归

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval.py tests/test_fusion.py `
  tests/test_source_filters.py tests/test_context.py tests/test_retrieval_failures.py `
  tests/test_evidence_diagnostics.py tests/test_hybrid_retrieval.py tests/test_comparison.py -q
```

上述测试同样使用小数据、受控模型输出或现成固定文件；不会运行真实语义评测脚本。
真实三组实验仍使用`examples/day09_compare.py run`，与本阶段验收分开。
