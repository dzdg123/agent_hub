# Day 09 阶段四：来源过滤

## 入口

```python
result = retriever.search(
    "PDF 页码如何记录？",
    candidate_k=6,
    top_k=3,
    filters={
        "file_types": {"pdf"},
        "relative_paths": {"document_tracking.pdf"},
    },
)
for rank, source in enumerate(result.final_sources, start=1):
    print(rank, source.title, source.score)
```

retrieve_candidates() 也支持相同的 filters 参数，返回两路未融合候选。

## 新增文件与接口

src/research_agent/source_filters.py：

| 函数 | 输入 | 输出与用途 |
|---|---|---|
| normalize_filters(filters) | 字典或 None；字段值为 set[str] / frozenset[str] | 返回独立、规范化后的集合字典，拒绝未知字段和非法类型 |
| resolve_allowed_ids(sources, filters=None) | 规范 Source 清单和过滤条件 | 无限制返回 None；有限制返回允许 ID 集合，无匹配则为空集合 |
| _relative_path(value) | 路径字符串 | 统一成正斜杠相对路径；拒绝绝对路径、盘符、父目录跳转和空路径，不读取文件系统 |

支持的条件：

- file_types：txt、markdown、pdf；类型名转小写并去掉两端空白。
- relative_paths：按规范 metadata.relative_path 匹配，可含目录；反斜杠统一为正斜杠。路径大小写保留并精确匹配，不猜测同名文件。
- 同一字段多个值按 OR；多个字段按 AND；显式 allowed_ids 再与这些条件取交集。
- 规范 metadata 缺少所需字段时不匹配，不根据 title、绝对 file_path 或 _retrieval 中的值推测。
- 同一文件多个片段均可入选，不按文件路径去重。

```python
filters = {
    "file_types": {"pdf", "markdown"},
    "relative_paths": {"notes.md", "guide.pdf"},
}
```

含义是类型属于 PDF 或 Markdown，并且路径属于 notes.md 或 guide.pdf。

## 空值及错误

| 条件 | 行为 |
|---|---|
| None 或 {} | 不限制来源 |
| {"file_types": set()} | 明确禁止所有来源 |
| {"relative_paths": set()} | 明确禁止所有来源 |
| 不存在的文件 | 允许集合为空，最终结果为空 |
| 未知过滤字段 | ValueError |
| 不支持的类型，例如 docx | ValueError |
| 字段值是 "pdf" 或 ["pdf"] | TypeError；要求字符串集合 |
| 绝对路径、../、空路径 | ValueError |

验证发生在搜索前，空白问题也不能绕过非法过滤条件检查。

## 两路调用流程

```text
用户 filters
    ↓ 验证与规范化
扫描规范 Source 清单 → filter_ids
    ↓ 与显式 allowed_ids 取交集
共同允许集合
    ├→ KeywordIndex：评分前过滤
    └→ ChromaIndex：where 限制后查询最近候选
    ↓
RRF → final_sources
```

Chroma 当前已经写入 filter_source_id，并在非空允许集合上使用：

```python
where = {"filter_source_id": {"$in": sorted(allowed_ids)}}
```

当前实现先按 IDs 读取实际存在的允许记录，检查过滤字段并计数，再令 n_results 不超过允许记录数量。未使用“先取 Top-k 再筛”的方式。

类型和文件路径在规范清单中解析，再统一转换成 ID，所以本阶段不需要额外写入 filter_file_type、filter_relative_path。以后需要数据库直接按这些字段查询时再添加。

实验脚本每次使用独立 Day 09 集合，不改旧 Day 08 库。旧集合若没有 filter_source_id，受限查询会明确报错，不能假定旧记录自动获得新字段。

## 诊断字段

CandidateResult 新增：

- filters：本次规范化后的条件，集合转为已排序列表便于 JSON 导出；无条件为 None，显式空集合保留为 []。
- requested_allowed_ids：调用方传入的显式 ID 限制，None 和 [] 分别保留。

现有 total_source_count、allowed_source_count、effective_candidate_k 分别显示总片段数、全部条件取交集后的片段数、实际候选上限。

所有条件及 ID 诊断都保存独立副本，调用方后来修改原集合不会改变本次结果。

## 命令行实验

在项目根目录运行真实模型，只查 PDF 并输出融合结果：

```powershell
.\.venv\Scripts\python.exe examples/day09_candidates.py --query "PDF 页码如何记录？" --file-type pdf --fuse
```

同时限制文件：

```powershell
.\.venv\Scripts\python.exe examples/day09_candidates.py --query "PDF 页码如何记录？" --file-type pdf --relative-path document_tracking.pdf --fuse
```

不存在文件：

```powershell
.\.venv\Scripts\python.exe examples/day09_candidates.py --query offset --relative-path missing.pdf --fuse
```

--file-type、--relative-path、--allowed-id 都可重复传入。--fuse 调用 search() 填充 final_sources；不加时保持阶段二候选输出。完整诊断继续写入 data/day09/candidates/<run-id>/candidates.json。

脚本仍会先建库，因此无匹配查询虽然不会调用 embed_query，但建库阶段仍会编码文档。

## 验证

tests/test_source_filters.py 覆盖解析、OR/AND、显式 ID 交集、同文件多片段、输入不变性、诊断快照及非法条件。

真实 Chroma + 受控 Embedder 集成测试构造前三条 TXT、后两条同文件 PDF，验证两路均在候选截断前限制范围，where 与 n_results 正确，融合结果全部来自 PDF；不存在文件不调用查询编码。

本阶段尚未实现上下文组装。后续应只将已过滤的 final_sources 送入上下文，并额外验证上下文的来源 ID 均属于允许集合。
