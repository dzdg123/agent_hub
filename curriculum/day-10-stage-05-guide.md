# 阶段五实现与审核用法

本阶段不调用 LLM Judge，不自动认证事实正确，也不更改旧工作流的报告发布路径。
`generate_answer()` 现在分别记录：

| 字段 | 值及含义 |
|---|---|
| structural_validation | passed / failed / not_run：JSON、Schema、状态和长度规则 |
| source_validation | passed / failed / not_run：唯一规范来源、可见 ID、连续原文摘录 |
| support_review | pending / passed / failed：调用方提交的人工或明确标记 AI 辅助审核 |

不执行的层用 `not_run`，例如空证据或没有取得模型回复；这不等于通过或失败。
程序两层通过后，`status` 仍是兼容的 `program_validated`，语义层默认 `pending`。
模型提交的 JSON 不能包含这些审核字段，不能为自己签发审核结论。

## 来源定位

`result.resolved_evidence` 按说法和引用顺序记录：

- `claim_index`、`evidence_index`：对应草稿中的位置，从 0 开始。
- `source_id`、`title`、`file_path`、`url`、`page`：只取自规范来源表。
- `occurrences`：摘录在该片段内的全部精确位置，包含重叠匹配。
- `local_start`、`local_end`：Source.content 中的左闭右开字符区间。
- `normalized_start`、`normalized_end`：可靠时为规范来源 offset 加局部位置，否则为 null。
- `offset_basis`：normalized_document_text / normalized_page_text，可靠性不足时为 null。

可靠条件包括：offset 和 end_offset 是非 bool 整数、区间非负、区间长度与正文字符数相等，
并且坐标基准与有无物理页码一致。来源页码若提供，必须为正整数。
这些是 Python 字符位置，不是原文件字节偏移，也不是 PDF 版面坐标。

## 提交实际审核

先执行原有生成流程：

```python
result = await generate_answer(model, question, scope, max_tokens=2048)
```

把问题、草稿及本次规范来源交给审核者。每条记录必须填写 reviewer、review_method、reason，
并逐项给出 `passed`、`failed` 或 `not_applicable`：

| checks 字段 | 审核内容 |
|---|---|
| directly_supported | 证据是否直接支持说法，是否反转否定关系或断章取义 |
| numbers_units_time_subject | 数字、单位、时间、主体是否被替换 |
| scope_not_expanded | 是否扩大了适用范围 |
| inference_labeled | 推断是否明确标记且没有冒充确定事实 |
| conflicts_not_hidden | 是否隐去了来源冲突或擅自选定结论 |
| question_addressed | 是否回应原问题 |

以下仅展示如何提交一个明确发现的错误，不能不经阅读照抄结论：

```python
from research_agent.rag_models import SupportChecks, SupportReviewRecord
from research_agent.rag_review import apply_support_reviews, can_publish_answer

record = SupportReviewRecord(
    draft_fingerprint=result.review_fingerprint,
    target="claim", index=0,
    reviewer="实际审核者姓名或标识",
    review_method="human",  # AI 辅助时必须明确填写 ai_assisted
    verdict="failed",
    reason="原文写未证明增长，说法却改成已证明增长。",
    checks=SupportChecks(
        directly_supported="failed",
        numbers_units_time_subject="passed",
        scope_not_expanded="passed",
        inference_labeled="not_applicable",
        conflicts_not_hidden="not_applicable",
        question_addressed="passed",
    ),
)
reviewed = apply_support_reviews(result, scope.visible_sources, [record])
assert reviewed.support_review == "failed"
assert not can_publish_answer(reviewed, scope.visible_sources)
```

审核对象包括：整份回答 `target="answer", index=None`、每条说法 `target="claim", index=N`，
以及每条局限 `target="limitation", index=N`。局限说明不是免审正文区。
必须完整覆盖且全部通过，整体才为 `passed`；任意失败即为 `failed`，尚未覆盖完则为 `pending`。
不能只改状态字段为 passed。说法必须检查支持关系，整份回答必须检查问题相关性。

`apply_support_reviews()` 返回副本，不改写原结果；同一对象不接受重复结论，
避免用后提交的 passed 覆盖已有 failed。更改内容后应重新生成并审核，而不是复用旧记录。

`review_fingerprint` 绑定问题、草稿和来源内容/定位信息，不包含检索分数与加载时间。
审核记录必须匹配当前版本；改变正文、引用、局限、问题、路径或页码后，旧记录失效。
这保证版本对应关系，不验证审核者身份，也不能保证其判断正确。

## 发布前检查与诊断保存

后续 Markdown 渲染或发布入口应先调用：

```python
if can_publish_answer(reviewed, scope.visible_sources):
    # 在这里接入后续受控渲染。
    ...
```

它会再次核对程序校验、版本指纹、审核覆盖范围，以及引用地址和页码等定位记录。
本阶段未接入旧的 `workflow._write_report()`，不能声称旧报告路径已执行这些检查。

`reviewed.model_dump_json(indent=2)` 可序列化全部用量、诊断、定位和审核记录。
文件/数据库持久化由调用方负责。

## 离线演示

```powershell
.\.venv\Scripts\python.exe examples/day10_review_lab.py
.\.venv\Scripts\python.exe -m pytest tests/test_rag_validation.py tests/test_rag.py -q
```

演示故意把“未证明增长”改成“已证明增长”，原文摘录真实，程序两层通过但审核仍 pending。
脚本随后提交一条预先填写、明确标记 AI 辅助示例的拒绝记录，展示 failed 与不能发布。
演示不调用真实 API，也没有实现自动语义判断。
