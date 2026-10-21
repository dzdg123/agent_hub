# Day 09 阶段七：失败与显式降级

入口仍为 `TwoBranchRetriever.search()`；新增 `allow_degraded=False` 和 `query_id=None`。
`retrieve_candidates()` 接受相同新参数，返回候选阶段状态，不执行融合。

```python
from research_agent.context import build_context

result = retriever.search(
    "offset", candidate_k=6, top_k=3,
    allow_degraded=True, query_id="q-007",
)
print(result.query_id, result.status)
for name, branch in result.branches.items():
    print(name, branch.status, branch.candidate_count, branch.elapsed_ms,
          branch.failure_stage, branch.error_type, branch.error_message)

if result.status == "failed":
    print("检索失败：", result.failure_reason)
else:
    if result.status == "degraded":
        print("已降级：", result.degraded_reason)
    context = build_context(result.final_sources, max_context_chars=2000)
    print(context.text)
```

## 状态契约

| 两路情况 | allow_degraded | 整体 status | search 的最终结果 |
| --- | --- | --- | --- |
| 都执行成功，至少一路有候选 | 任意 | ok | 正常 RRF |
| 都执行成功，都无候选 | 任意 | empty | [] / final_count=0 |
| 一路失败，另一路成功（可为空） | True | degraded | 对正常分支做 RRF，可能是 [] |
| 一路失败，另一路成功 | False（默认） | failed | final_sources/final_count/fusion 均为 None |
| 两路都失败 | 任意 | failed | 同上 |
| 空白问题或没有允许来源 | 任意 | skipped | [] / final_count=0，不查询或初始化分支 |

分支 `BranchResult.status` 为 ok/empty/failed/skipped。
成功但无候选的分支 candidate_count=0；失败分支 candidate_count=None，表示未得到有效候选，
sources/traces 为 []，不能将其解释为已完成搜索但没有资料。
所有参数和过滤条件在跳过查询前也会校验。

候选接口 retrieve_candidates 的 final_sources/final_count/fusion 一直为 None，
应通过 .search() 获取可交给上下文构建器的融合结果。

## 错误边界

`src/research_agent/retrieval_errors.py` 新增：

| 接口 | 作用 |
| --- | --- |
| RetrievalOperationalError(message, *, operation=None, error_type=None) | 协调层唯一捕获的可降级错误；数据/配置错误不继承它 |
| operational_boundary(operation, *, expected_errors=()) | 上下文管理器，在底层调用边界将已知运行错误包装并通过 raise ... from exc 保留原因 |

当前白名单：模型加载/编码、Chroma 操作边界内的 OSError（包括 TimeoutError、ConnectionError 等），
Chroma 的 RateLimitError，以及 SQLite 明确的 SQLITE_BUSY/SQLITE_LOCKED。
SQLite 其他 OperationalError、通用 RuntimeError、Chroma InternalError 等未知类型原样抛出。
不按错误消息字符串猜测“是否可降级”。将来新增故障类型时需要先确认具体类型与语义，再扩展白名单。

不能捕获所有 RuntimeError，因为 IndexDataError、IndexConfigurationError 也继承它。
Embedding 模型初始化原来的 except Exception 已移除；模型输出非法、维度不匹配、来源冲突、
参数错误、缺少依赖和未分类程序错误不会变成降级结果。

直接调用 ChromaIndex 仍会抛出故障；已识别的 IO 故障现在抛 RetrievalOperationalError，
原始 OSError 在 __cause__ 中。只有协调层按开关决定返回 failed 还是 degraded。
自定义索引若要参与降级，应在自己的明确运行边界抛该专用错误；未适配的 OSError 不由协调层泛捕获。

## 初始化也需要进入契约

如果在调用 search 之前直接加载模型，加载失败时协调器尚未获得控制。
可使用 `retrieval_pipeline.LazyCandidateIndex(factory)`：

```python
from research_agent.embeddings import SentenceTransformerEmbedder
from research_agent.retrieval import ChromaIndex, KeywordIndex
from research_agent.retrieval_pipeline import LazyCandidateIndex, TwoBranchRetriever

keyword = KeywordIndex()
keyword.add(sources)  # 加载器提供的规范来源

def open_vector():
    model = SentenceTransformerEmbedder()  # 实验中沿用已固定的模型/版本配置
    return ChromaIndex("已有的独立Day09库目录", embedder=model)

retriever = TwoBranchRetriever(
    sources, keyword_index=keyword,
    vector_index=LazyCandidateIndex(open_vector),
)
```

上例要求已存在的库与规范 sources 完全一致；新库应在 factory 内用规范 Source 建库后返回。
LazyCandidateIndex 的 ready() 成功后缓存索引；失败不缓存，下一个请求可重试。
all()/search() 委托给准备好的索引。它不自行捕获未知异常，也不提供异步调度。

现有非 lazy 索引仍在协调器构造时检查一致性；已知运行错误延后到查询内重新检查并报告，
来源冲突立即抛出。lazy 索引在请求内准备后检查，不绕过任何来源校验。

## 诊断与计时

CandidateResult 新增 query_id（未传自动生成唯一 ID）、status、allow_degraded、failure_reason。
原 degraded_reason 用于解释实际降级，严格模式失败原因写在 failure_reason。
分支名由 branches 的 key 提供，所有分支诊断关联父级 query_id。

BranchResult 新增 error_type、error_message、failure_stage、error_operation。
failure_stage 区分 initialization、validation_read、search；error_operation 指明更具体的底层操作。
包装后的诊断保留原始异常类型名，内存中的异常链保留原始原因。

elapsed_ms 现在覆盖该请求的分支准备（若需要）、规范清单读取校验和搜索；
失败也有耗时。首次 lazy 初始化可能包含模型加载或建库时间，与先前只测 search 的耗时不能直接比较。
两路仍串行运行，不加重试调度。单路运行失败后仍执行另一路收集诊断；
遇到一致性或程序错误则直接抛出，不返回部分结果。

## 实验入口

```powershell
.\.venv\Scripts\python.exe examples/day09_failures.py
```

使用受控索引模拟两路正常、空命中、双向单路故障、严格模式、两路都失败和初始化失败。
共 9 个案例，预期状态计数 ok=2、empty=1、failed=2、degraded=4。
`run_demo()` 返回记录和分类统计；`main()` 打印并保存
`data/day09/failures/<独立目录>/failures.json`，包含诊断、候选、轨迹和可用上下文。
失败案例 context=null。该演示不代表真实语义检索效果。

原真实/受控候选脚本也支持新参数：

```powershell
.\.venv\Scripts\python.exe examples/day09_candidates.py --smoke --fuse `
  --allow-degraded --query-id q-007
```

去掉 --smoke 使用原固定数据和模型。向量加载与独立集合建库已移入 lazy factory，
初始化运行故障可以按开关处理。不会修改旧 Day08 库。

降级结果和失败结果单独统计。examples/day09_fusion.py 的 load_saved_candidates()
拒绝 degraded/failed 或包含 failed 分支的候选；使用它的阶段五、六重放入口同样受此保护，
避免将单路候选伪装为完整双路公平对照。实际降级查询仍可直接把 search 的 final_sources 交给 build_context。

## 验证

`tests/test_retrieval_failures.py` 覆盖严格/降级模式、两路失败、失败加空命中、
初始化失败与恢复、读取失败、耗时、问题 ID、来源冲突、非法过滤与程序错误传播、
真实 Chroma API 上注入的限流/读取故障、模型错误分类、CLI 诊断和独立统计。
原 tests/test_vector_index.py 的 IO 断言更新为检查包装异常及原始 cause，仍要求故障向外报告。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval_failures.py `
  tests/test_hybrid_retrieval.py tests/test_embeddings.py tests/test_chroma_index.py `
  tests/test_vector_index.py tests/test_source_filters.py tests/test_fusion.py `
  tests/test_context.py tests/test_evidence_diagnostics.py tests/test_workflow.py -q
```

演示和当前 candidates.json 保留完整候选便于学习；以后处理敏感文档时应另行限制持久化正文和错误消息范围。
