# Day 05 固定案例与验收证据

验收日期：2026-09-30。所有下列结果来自本次实际运行；全部使用离线假模型和本地工具。
新案例在 `tests/test_day05_acceptance.py`，原有练习仍在 `tests/test_mini_agent.py`。

M 为实际 complete 次数，T 为提交 Registry 次数，H 为实际 handler 开始执行次数。
M 不等同于返回 Usage 中的 model_calls；校验失败及未知工具计入 T，但不计入 H。
表内“通过”同时验证状态、终止原因、唯一终止事件及实际调用证据，不只检查假模型的最终文字。

| ID | 场景 / 输入 | 测试函数或参数 ID | 实际状态 / 原因 | M/T/H | 关键证据 | 结果 |
|---|---|---|---|---|---|---|
| D05-01 | 普通 API 解释 | test_d05_01_plain_answer | completed/final_answer | 1/0/0 | 最后一条 assistant，未调用 Registry | 通过 |
| D05-02 | calculator: 12 * 8 | test_d05_tool_roundtrip[D05-02] | completed/final_answer | 2/1/1 | 下一轮 tool.content=96；请求/结果 ID 一致 | 通过 |
| D05-03 | current_time | test_d05_tool_roundtrip[D05-03] | completed/final_answer | 2/1/1 | ISO 时间可解析，UTC 偏移为 0 | 通过 |
| D05-04 | text_statistics: hello agent | test_d05_tool_roundtrip[D05-04] | completed/final_answer | 2/1/1 | characters=11、non_whitespace=10、words=2 | 通过 |
| D05-05 | Agent agent AGENT，忽略大小写 | test_d05_tool_roundtrip[D05-05] | completed/final_answer | 2/1/1 | 返回 {"text":3}，保留当前契约 | 通过 |
| D05-06 | unknown_tool | test_d05_tool_roundtrip[D05-06] | completed/final_answer | 2/1/0 | ok=False、未知工具；所有 handler 均未执行 | 通过 |
| D05-07 | calculator: {} | test_d05_tool_roundtrip[D05-07] | completed/final_answer | 2/1/0 | Pydantic missing 错误回传；handler 未执行 | 通过 |
| D05-08 | expression=123 / unexpected=True | test_d05_tool_roundtrip[D05-08-type/extra] | completed/final_answer | 各 2/1/0 | string_type / extra_forbidden；两种输入都拒绝 | 两项通过 |
| D05-09 | calculator: 1 / 0 | test_d05_tool_roundtrip[D05-09] | completed/final_answer | 2/1/1 | handler 确实执行，ZeroDivisionError 被封装并回传 | 通过 |
| D05-10 | 同轮 2+2 与 3*3 | test_d05_10_multiple_tools | completed/final_answer | 2/2/2 | handler 顺序正确；calc-1→4、calc-2→9 | 通过 |
| D05-11 | 空字符串、空格、换行制表符 | test_d05_11_empty_reply | failed/empty_response | 各 1/0/0 | 不再调用工具；原始空白回复保留 | 三项通过 |
| D05-12 | 抛 LLMError | test_d05_12_model_error | failed/model_error | 1/0/0 | error.type/message 保留；没有后续调用 | 通过 |
| D05-13 | 每轮请求 1+1，上限 3 | test_d05_13_max_steps | stopped/max_steps | 3/3/3 | 最后一份结果保留，无第 4 轮；每轮看到此前结果 | 通过 |
| D05-14 | 开始前取消 | test_d05_14_cancel_before_start | cancelled/user_cancelled | 0/0/0 | 只有 run_started/run_finished；steps=0 | 通过 |
| D05-15 | 第一项工具完成后取消 | test_cancel_boundaries[D05-15] | cancelled/user_cancelled | 1/1/1 | 4 已保存；第二项 3*3 不执行，无下一轮模型 | 通过 |

说明：D05-08 表中斜杠合并显示两个节点；实际运行时使用 `D05-08-type` 或 `D05-08-extra`。
失败工具案例的 completed 表示模型在收到失败结果后给出最终回复，绝不表示工具成功。
这些脚本验证执行流程，不证明真实模型能自主发现或修复错误。

## 额外的工程验收

| 测试 | 证明的行为 | 结果 |
|---|---|---|
| test_cancel_boundaries 的 4 个 callback 参数 | 回调设置取消后不启动模型/工具，run_started 也可取消 | 通过 |
| test_cancel_during_tool_preserves_finished_work | Event 精确控制在途工具，取消标志不强制打断它，保存结果后停止 | 通过 |
| test_run_isolation_and_snapshots | 同一 Agent 连续运行 UUID/消息/用量独立；首轮快照固定；回调只能修改副本 | 通过 |
| test_programming_error_is_not_service_failure | AssertionError 继续抛出，不被伪装成 failed 服务错误 | 通过 |
| test_trace_export_roundtrip | JSONL/JSON 可往返还原；重复写入不覆盖；拒绝路径型 run_id | 通过 |
| test_cli_ask_compatibility_offline | mock 客户端验证 ask 入口仍支持二元组；真实工具输出 96 | 通过 |

## 重现命令

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_day05_acceptance.py -v
.\.venv\Scripts\python.exe -m pytest tests/test_mini_agent.py tests/test_tools.py tests/test_day05_acceptance.py tests/test_llm.py -q
.\.venv\Scripts\python.exe examples/day05_agent_v0.py
```

若 pytest 默认临时目录有权限问题，先确保 `data/day05` 存在，再选择新的、专用于测试的 basetemp 子目录；不得指定项目根目录。

本次最终全量命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp data/day05/pytest-final-20260930 --junitxml=data/day05/pytest-final.xml
```

实测：**100 passed, 1 warning in 5.29s**。其中新增验收文件 27 项；全量 JUnit 证据位于 `data/day05/pytest-final.xml`，被 Git 忽略。
唯一 warning 是 Starlette 使用 AnyIO 已弃用别名，不影响本次断言。pytest 总数不等于课程场景数。
