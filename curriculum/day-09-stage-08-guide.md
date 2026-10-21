# Day 09 阶段八：公平的三组对比

实验入口：`examples/day09_compare.py`。核心计算：`src/research_agent/comparison.py`。
主表仅比较 KeywordIndex、真实 ChromaIndex、两路 RRF。不会用受控向量替代真实语义结果。

## 运行与审核

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe examples/day09_compare.py run
```

默认使用 Day08 原 retrieval-v1 数据和模型快照；原10道正向题、2道探针、来源ID、切片和加载配置均完整保留。
创建独立 `data/day09/comparison/<运行目录>/chroma`，不修改原库。
另加 curriculum/day09-challenge-v1.jsonl 的6道挑战题，正向分母为5，过滤后无答案题为1。

每个问题两路各取一次最多6条候选，关键词不足6条时保留实际数量。
独立方法取各自前三，RRF输入各路完整候选后取前三；三组使用相同的2000 Python字符预算。
rank_constant=60，top_k固定3，allow_degraded=False。
candidate_k可以调整，但必须记录为不同配置；top_k不能任意调整后仍将指标称为Hit@3。

```powershell
.\.venv\Scripts\python.exe examples/day09_compare.py run `
  --candidate-k 6 --max-context-chars 2000 --note "initial three-way comparison"
```

结果目录包含：

| 文件 | 内容 |
| --- | --- |
| config.json | 查询前冻结的原数据指纹、挑战文件SHA256、题目、证据、过滤、模型与参数 |
| length_audit.json | 模型文档和问题长度审计，不作为DeepSeek上下文token预算 |
| raw_results.json | 规范来源快照、两路原候选/轨迹、三组Top-3、上下文、逐题计时 |
| raw_integrity.json | 原始结果SHA256，报告生成前检查 |
| review.csv | 原始候选并集的待审核表，按问题ID和source_id去重 |
| summary.json | 分组指标和逐题判断；待审核或实验不完整时正式成绩为null |
| report.md | 三组主表、自动辅助核对、成本、实际差异分析和候选正文 |
| reports/*.json | 每次report的审核和成绩快照 |

初始化/预热发生明确运行故障时保存failure.json并抛出；不回退到假向量。
正式查询单路故障则记录整题failed，继续保存后续问题，失败题不删除。
数据冲突、非法过滤、未知程序错误直接拒绝处理。

在review.csv中只填写四列：

| 列 | 填写方式 |
| --- | --- |
| support_level | 0=无关/不支持，1=相关但缺关键证据，2=正文直接支持；未审核留空 |
| reason | 基于正文的实际支持或不支持理由，每个已评分候选必填 |
| reviewer | 审核者；AI辅助请明确写AI与工具/模型标识 |
| human_checked | yes/no或留空；AI辅助后需人工抽查关键成功与失败样例 |

同一问题同一来源在三种方法中复用同一评分，不按方法重复打分。
审核覆盖两路各最多6条候选的并集，因为RRF可能将某路第4～6名提到前三。
其余列、候选数量和原始正文不允许改动。CSV采用UTF-8 BOM，正文可能包含换行，需用标准CSV工具编辑。

```powershell
.\.venv\Scripts\python.exe examples/day09_compare.py report `
  --run-dir data/day09/comparison/<运行目录>
```

report仅更新报告和保存修订快照，不覆盖已填写的review.csv。
不自动用“预标注ID命中”或相似度推测支持等级。未完成审核时输出待审核报告是正常行为。

## 题组

原始基线沿用Day08 questions.jsonl和probes.jsonl，不改题目、来源和分母。
挑战题独立版本位于curriculum而非生成结果目录，便于版本管理：

| ID | 类型 | 固定支持依据 |
| --- | --- | --- |
| C01 | tool_call_id精确术语 | tools.md的工具结果关联原调用ID说明 |
| C02 | 包版本冲突同义改写 | environment.txt的依赖隔离说明 |
| C03 | 物理页与印刷页码干扰 | document_tracking.pdf物理第3页 |
| C04 | 同题只允许PDF | 同上 |
| C05 | 同题只允许指定PDF文件 | 同上 |
| C06 | offset问题只允许cooking.txt | 允许范围内无支持证据，不进入正向分母 |

load_questions会在检索前验证关键句确实存在于规范片段、过滤条件有效、
声明的has_allowed_evidence与固定关键句及允许范围一致、query_id不冲突。
此验证用于预标注核对，不替代对所有返回候选的正文审核。
新增资料/题目请另存版本并通过--dataset-root、--challenges指定，不修改原基线。

## 指标和分母

基线正向分母固定10、挑战正向分母固定5；无证据题分别2和1，单独保留。
每种方法按组输出Hit@3、Top-1支持率、上下文保留命中率及对应命中数量。
只统计等级2为直接支持。空候选的成功查询记未命中，不要求人工填写不存在的候选行。
任一正向题失败或所需Top-3未审核，该组该方法完整命中率保持null，分母仍然保留。

不支持候选总数统计Top-3等级0，等级1另列；该计数包含该组探针，范围与正向命中率不同。
逐题另存RRF相对向量新增的不支持ID、Top-1是否改变和三组支持等级。
无证据探针返回候选并不表示有答案，必须看正文；发现等级2时需人工检查题目或预标注是否有误。
当前实现不增加拒绝阈值，也不将“返回空列表”当作无答案判断的唯一标准。

候选重复率在融合前计算：

```text
每题raw = keyword候选数 + vector候选数
每题unique = 两路source_id并集大小
组内rate = Σ(raw - unique) / Σraw；总数0时为0
```

不同问题之间不合并ID。跨路重合本身是RRF有用信号，不解释为越低越好。
过滤违规分别检查三组Top-3和真正放入上下文的ID，正常结果应全为0。
协调器在候选阶段也会拒绝越过allowed_ids的返回值。

## 耗时

模型加载、关键词建库、向量建库、协调器验证、两路首次预热分别计时。
使用固定Q01各预热一次，不计入18道正式查询和命中统计。
已有磁盘缓存状态可能影响模型加载时间；此处记录的是本进程初始化，不能宣称清空缓存的系统冷启动。

TimedCandidateIndex只测search调用；协调器原elapsed_ms包含all()来源校验，仍单独保留。
keyword/vector成本用各自热search时间；RRF成本用两路串行热search时间之和加融合时间。
三组context_ms分别记录；报告给出上下文字符均值，原始文件可查看逐题text、included/omitted及理由。

## 函数入口

| 所在文件 | 接口 | 作用 |
| --- | --- | --- |
| comparison.py | TimedCandidateIndex(index) | 代理all/search，保存最近一次search耗时 |
| 同上 | compare_query(retriever, canonical_sources, entry, *, ...) | 单题只召回一次两路，生成三组排名、预算上下文和诊断 |
| 同上 | make_review_rows(raw) | 按问题ID+source_id合并审核记录，保留分支排名 |
| 同上 | aggregate_comparison(raw, rows) | 校验审核表，生成分组及逐题指标 |
| 同上 | render_comparison_report(raw, summary, rows) | 生成主表、成本、优势/退化记录和正文审核表 |
| day09_compare.py | load_questions(labels, sources, challenges) | 合并原基线与独立挑战组，验证固定依据 |
| 同上 | run_comparison(dataset, challenges, *, ...) | 真模型加载、一次建库、预热、18题运行、保存结果 |
| 同上 | report(run_dir) | 校验完整性、读取审核、保存报告和修订快照 |
| 同上 | save_review(run_dir, raw) | 在新运行目录独占创建空审核表 |
| 同上 | main() | run/report命令行入口 |

差异分析优先比较(Hit, Top-1支持)，显示实际ID和审核理由，不根据分数编造原因。
尚未审核时写待审核；已审核数据没有某类差异则明确写未观察到。
独立机制演示可运行`examples/day09_fusion.py --demo`，不得混作真实数据结果。

## 本次验证运行

真实运行目录：data/day09/comparison/20261021T063812Z-c0173b75。
18道题均完成，没有分支失败；检索和上下文过滤违规均为0。
首次运行生成121条去重审核记录，正式正文支持率仍需填写review.csv后计算。

预标注ID辅助核对（不等于人工Hit@3）：

| 题组 | 关键词 | 向量 | RRF |
| --- | --- | --- | --- |
| 原10题 | 9/10 | 10/10 | 9/10 |
| 挑战正向5题 | 4/5 | 5/5 | 4/5 |

因此不能假设融合必然提高命中；应抽查导致该差异的实际正文和排名。
报告生成后人工审核不会改变原候选及原始结果。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_comparison.py tests/test_hybrid_retrieval.py `
  tests/test_fusion.py tests/test_context.py tests/test_source_filters.py -q
```

测试覆盖一次召回/相同窗口、完整6候选参与融合、预算丢失命中、不同题组分母、
无候选与失败区别、审核防篡改、待审核null、原10+2保留、过滤及挑战证据声明检查。
