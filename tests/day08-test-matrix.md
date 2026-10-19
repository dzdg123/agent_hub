# Day 08 阶段九测试映射

普通自动测试使用假模型/假 Embedder，不下载模型。数学函数只依赖标准库；测试运行器使用 pytest。
Chroma 集成测试操作临时真实数据库，未安装 Chroma 时显式 skip，并提示安装 .[vector]。
阶段七固定资料通过独立加载测试；阶段八真实语义结果与自动化存储测试分别记录。

| 编号 | 自动验证位置 | 核心断言 |
| --- | --- | --- |
| M01 | test_vector_math.py | 同向、正交、反向、缩放；空向量、零向量、维度不一致、非有限数明确失败 |
| V01 | test_chroma_index.py | 空写入不调用 Embedder，空库计数不变 |
| V02 | test_chroma_index.py | 同 ID upsert 更新正文，计数不增长 |
| V03 | test_chroma_index.py、test_vector_index.py | 可控向量排序，cosine distance 为 0/1/2，score 为 1/0/-1 |
| V04 | test_vector_index.py | top_k 超过记录数时仅返回现有数量，传给库的 n_results 确为 count |
| V05 | 两个索引测试文件 | 空库、空白问题不编码；非法 top_k（含 bool）即使在空输入时也报错 |
| V06 | test_chroma_index.py | 完整 Source 往返，包括 URL、路径、PDF 页、offset、嵌套 metadata、空白页警告、原始时间 |
| V07 | test_vector_index.py | 删除 doc-1 不误删 doc-10/doc-100；空列表不删除其余记录 |
| V08 | test_vector_index.py | 删除后新对象打开同一路径，不 add 仍能查询；删除 ID 不恢复，完整来源仍在 |
| V09 | test_chroma_index.py、test_embeddings.py | 数量/维度错误在 upsert 前拒绝，重开后仍按已有维度校验 |
| V10 | 三个模型/索引测试文件 | NaN/Inf/零向量拒绝；空白文档批次不编码不写入；非法查询向量不传入库 |
| V11 | 索引测试文件、test_embeddings.py | 损坏来源信息和数据库错误显式报错；模型加载失败保留底层原因 |
| V12 | test_embeddings.py、test_vector_index.py | 特殊 token 和查询指令计入长度；正好上限可编码，超长问题/文档在编码及写入前拒绝 |
| 依赖隔离 | test_vector_imports.py | 新进程阻止全部 vector 相关导入；基础 retrieval 仍可用，显式初始化时提示安装 vector |

## 运行

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_vector_math.py tests/test_vector_imports.py tests/test_embeddings.py tests/test_chroma_index.py tests/test_vector_index.py tests/test_documents.py tests/test_retrieval.py -q
.\.venv\Scripts\python.exe -m pip check
```

若宿主 pytest 临时目录不可写，可将 --basetemp 指向项目内一个新的专用临时目录。
注意 pytest 会清理指定目录，不能使用语料目录、数据库目录或其他已有重要目录。

## 真实语义和跨进程验收

真实模型评测继续使用 examples/day08_evaluate_retrieval.py 和固定问题表，不在普通 pytest 收集时下载或加载模型。
AI 辅助内容审核结果已记录在 data/day08/retrieval-evaluation/20261019T023647Z-9458be24/，不是独立人类评审。
不对真实模型硬编码浮点得分，也不用假向量测试声称模型理解中文。
两个独立进程的持久化验证使用 examples/day08_chroma_persistence_lab.py build/reopen；自动 V08 是同路径新对象验证。

## 本次验证记录（2026-10-19）

上述七个测试文件共 115 项通过，使用 HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1；未执行真实模型下载或语义重新评分。
Chroma 存储测试实际运行，未被 skip。46 条警告来自已安装 Chroma 的 legacy embedding function config 弃用提示。
pip check 输出 No broken requirements found。本次未改动 runtime 默认索引或原始评测标签。
