# Day 09 三组检索对比

运行：20261021T063812Z-c0173b75

配置：candidate_k=6，top_k=3，rank_constant=60，Python字符预算=2000。

正式指标依据 review.csv 的正文审核；预标注 ID 命中只用于核对。空候选是未命中；失败题保留分母并使成绩不完整。

待审核候选：121；人工抽查记录：0。

| 题组 | 方法 | 正向分母 | Hit@3 | Top-1支持率 | 预算后命中率 | 过滤违规（检索/上下文） |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | keyword | 10 | 待审核/执行不完整 | 待审核/执行不完整 | 待审核/执行不完整 | 0/0 |
| baseline | vector | 10 | 待审核/执行不完整 | 待审核/执行不完整 | 待审核/执行不完整 | 0/0 |
| baseline | rrf | 10 | 待审核/执行不完整 | 待审核/执行不完整 | 待审核/执行不完整 | 0/0 |
| challenge | keyword | 5 | 待审核/执行不完整 | 待审核/执行不完整 | 待审核/执行不完整 | 0/0 |
| challenge | vector | 5 | 待审核/执行不完整 | 待审核/执行不完整 | 待审核/执行不完整 | 0/0 |
| challenge | rrf | 5 | 待审核/执行不完整 | 待审核/执行不完整 | 待审核/执行不完整 | 0/0 |

## 解释性自动核对与成本

下面的预标注ID命中仅核对预先固定的来源，不替代正文审核；耗时均为本次实测。

| 题组 | 方法 | 预标注ID命中/正向分母 | 不支持(0级)/主题相关(1级) | 热检索均值ms | 上下文均值字符 |
| --- | --- | --- | --- | --- | --- |
| baseline | keyword | 9/10 | None/None | 0.8660916743489603 | 1244.9166666666667 |
| baseline | vector | 10/10 | None/None | 19.123433346976526 | 1306.6666666666667 |
| baseline | rrf | 9/10 | None/None | 21.003933356648 | 1275.3333333333333 |

baseline 融合前重复率：(135-95)/135 = 29.6%；空分母按0。

| challenge | keyword | 4/5 | None/None | 0.5189166695345193 | 957.8333333333334 |
| challenge | vector | 5/5 | None/None | 16.837283338342484 | 1067.5 |
| challenge | rrf | 4/5 | None/None | 18.174166665024433 | 1043 |

challenge 融合前重复率：(43-26)/43 = 39.5%；空分母按0。


启动和预热（与热查询分开）：

| 阶段 | 实测值 |
| --- | --- |
| model_load_ms | 10056.710199976806 |
| keyword_build_ms | 0.3825000021606684 |
| vector_build_ms | 1456.4620000310242 |
| coordinator_validation_ms | 5.6433999561704695 |
| warmup_question_id | Q01 |
| keyword_warmup_ms | 0.9938000002875924 |
| vector_warmup_ms | 24.405699979979545 |

| 问题 | 关键词 Top-3 | 向量 Top-3 | RRF Top-3 | 三路 Hit | 预算后证据（K/V/R） | 解释 |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | doc-67e8db8df1d1d15d, doc-1d7abc3ef0be35c3, doc-f69a71b5b9f84c38 | doc-67e8db8df1d1d15d, doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985 | doc-67e8db8df1d1d15d, doc-47de7bf8c30cf985, doc-f69a71b5b9f84c38 | 待定/待定/待定 | doc-67e8db8df1d1d15d, doc-1d7abc3ef0be35c3, doc-f69a71b5b9f84c38 / doc-67e8db8df1d1d15d, doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985 / doc-67e8db8df1d1d15d, doc-47de7bf8c30cf985, doc-f69a71b5b9f84c38 | 正向题；ok；相对向量新增0级：None |
| Q02 | doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d | doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d | doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d | 待定/待定/待定 | doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d / doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d / doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d | 正向题；ok；相对向量新增0级：None |
| Q03 | doc-21a31aa34e21153f, doc-84a31f89a1acc2f3, doc-eccf50f58a9a4d9d | doc-21a31aa34e21153f, doc-f69a71b5b9f84c38, doc-67e8db8df1d1d15d | doc-21a31aa34e21153f, doc-eccf50f58a9a4d9d, doc-67e8db8df1d1d15d | 待定/待定/待定 | doc-21a31aa34e21153f, doc-84a31f89a1acc2f3, doc-eccf50f58a9a4d9d / doc-21a31aa34e21153f, doc-f69a71b5b9f84c38, doc-67e8db8df1d1d15d / doc-21a31aa34e21153f, doc-eccf50f58a9a4d9d, doc-67e8db8df1d1d15d | 正向题；ok；相对向量新增0级：None |
| Q04 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-f69a71b5b9f84c38 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 | 待定/待定/待定 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 / doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-f69a71b5b9f84c38 / doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 | 正向题；ok；相对向量新增0级：None |
| Q05 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-f69a71b5b9f84c38 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-f69a71b5b9f84c38 | 待定/待定/待定 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 / doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-f69a71b5b9f84c38 / doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-f69a71b5b9f84c38 | 正向题；ok；相对向量新增0级：None |
| Q06 | doc-870ad51e4b6db443, doc-1d7abc3ef0be35c3, doc-c5b5b52aa10f6be7 | doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-a4d971350c7e5875 | doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-c5b5b52aa10f6be7 | 待定/待定/待定 | doc-870ad51e4b6db443, doc-1d7abc3ef0be35c3, doc-c5b5b52aa10f6be7 / doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-a4d971350c7e5875 / doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-c5b5b52aa10f6be7 | 正向题；ok；相对向量新增0级：None |
| Q07 | doc-76ab5ce75e586d60, doc-c5b5b52aa10f6be7, doc-8ed6ac9b3a883cfc | doc-76ab5ce75e586d60, doc-5149b57efb060e06, doc-47de7bf8c30cf985 | doc-76ab5ce75e586d60, doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985 | 待定/待定/待定 | doc-76ab5ce75e586d60, doc-c5b5b52aa10f6be7, doc-8ed6ac9b3a883cfc / doc-76ab5ce75e586d60, doc-5149b57efb060e06, doc-47de7bf8c30cf985 / doc-76ab5ce75e586d60, doc-c5b5b52aa10f6be7, doc-47de7bf8c30cf985 | 正向题；ok；相对向量新增0级：None |
| Q08 | doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d | doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985, doc-76ab5ce75e586d60 | doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985, doc-76ab5ce75e586d60 | 待定/待定/待定 | doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d / doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985, doc-76ab5ce75e586d60 / doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985, doc-76ab5ce75e586d60 | 正向题；ok；相对向量新增0级：None |
| Q09 | doc-eccf50f58a9a4d9d, doc-47de7bf8c30cf985, doc-84a31f89a1acc2f3 | doc-eccf50f58a9a4d9d, doc-47de7bf8c30cf985, doc-21a31aa34e21153f | doc-eccf50f58a9a4d9d, doc-47de7bf8c30cf985, doc-c5b5b52aa10f6be7 | 待定/待定/待定 | doc-eccf50f58a9a4d9d, doc-47de7bf8c30cf985, doc-84a31f89a1acc2f3 / doc-eccf50f58a9a4d9d, doc-47de7bf8c30cf985, doc-21a31aa34e21153f / doc-eccf50f58a9a4d9d, doc-47de7bf8c30cf985, doc-c5b5b52aa10f6be7 | 正向题；ok；相对向量新增0级：None |
| Q10 | doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443, doc-1d7abc3ef0be35c3 | doc-8ed6ac9b3a883cfc, doc-f69a71b5b9f84c38, doc-5149b57efb060e06 | doc-8ed6ac9b3a883cfc, doc-eccf50f58a9a4d9d, doc-21a31aa34e21153f | 待定/待定/待定 | doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443, doc-1d7abc3ef0be35c3 / doc-8ed6ac9b3a883cfc, doc-f69a71b5b9f84c38, doc-5149b57efb060e06 / doc-8ed6ac9b3a883cfc, doc-eccf50f58a9a4d9d, doc-21a31aa34e21153f | 正向题；ok；相对向量新增0级：None |
| N01 | doc-1d7abc3ef0be35c3, doc-c5b5b52aa10f6be7, doc-870ad51e4b6db443 | doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443, doc-5149b57efb060e06 | doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443, doc-1d7abc3ef0be35c3 | 待定/待定/待定 | doc-1d7abc3ef0be35c3, doc-c5b5b52aa10f6be7, doc-870ad51e4b6db443 / doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443, doc-5149b57efb060e06 / doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443, doc-1d7abc3ef0be35c3 | 无允许证据，不计分母；ok；相对向量新增0级：None |
| N02 | doc-1d7abc3ef0be35c3, doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443 | doc-c5b5b52aa10f6be7, doc-8ed6ac9b3a883cfc, doc-f69a71b5b9f84c38 | doc-8ed6ac9b3a883cfc, doc-c5b5b52aa10f6be7, doc-1d7abc3ef0be35c3 | 待定/待定/待定 | doc-1d7abc3ef0be35c3, doc-8ed6ac9b3a883cfc, doc-870ad51e4b6db443 / doc-c5b5b52aa10f6be7, doc-8ed6ac9b3a883cfc, doc-f69a71b5b9f84c38 / doc-8ed6ac9b3a883cfc, doc-c5b5b52aa10f6be7, doc-1d7abc3ef0be35c3 | 无允许证据，不计分母；ok；相对向量新增0级：None |
| C01 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-76ab5ce75e586d60 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-21a31aa34e21153f | 待定/待定/待定 | doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-84a31f89a1acc2f3 / doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-76ab5ce75e586d60 / doc-47de7bf8c30cf985, doc-eccf50f58a9a4d9d, doc-21a31aa34e21153f | 正向题；ok；相对向量新增0级：None |
| C02 | doc-67e8db8df1d1d15d, doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985 | doc-67e8db8df1d1d15d, doc-c5b5b52aa10f6be7, doc-21a31aa34e21153f | doc-67e8db8df1d1d15d, doc-f69a71b5b9f84c38, doc-21a31aa34e21153f | 待定/待定/待定 | doc-67e8db8df1d1d15d, doc-f69a71b5b9f84c38, doc-47de7bf8c30cf985 / doc-67e8db8df1d1d15d, doc-c5b5b52aa10f6be7, doc-21a31aa34e21153f / doc-67e8db8df1d1d15d, doc-f69a71b5b9f84c38, doc-21a31aa34e21153f | 正向题；ok；相对向量新增0级：None |
| C03 | doc-870ad51e4b6db443, doc-8ed6ac9b3a883cfc, doc-1d7abc3ef0be35c3 | doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-a4d971350c7e5875 | doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-8ed6ac9b3a883cfc | 待定/待定/待定 | doc-870ad51e4b6db443, doc-8ed6ac9b3a883cfc, doc-1d7abc3ef0be35c3 / doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-a4d971350c7e5875 / doc-870ad51e4b6db443, doc-5149b57efb060e06, doc-8ed6ac9b3a883cfc | 正向题；ok；相对向量新增0级：None |
| C04 | doc-5149b57efb060e06, doc-a4d971350c7e5875 | doc-5149b57efb060e06, doc-a4d971350c7e5875 | doc-5149b57efb060e06, doc-a4d971350c7e5875 | 待定/待定/待定 | doc-5149b57efb060e06, doc-a4d971350c7e5875 / doc-5149b57efb060e06, doc-a4d971350c7e5875 / doc-5149b57efb060e06, doc-a4d971350c7e5875 | 正向题；ok；相对向量新增0级：None |
| C05 | doc-5149b57efb060e06, doc-a4d971350c7e5875 | doc-5149b57efb060e06, doc-a4d971350c7e5875 | doc-5149b57efb060e06, doc-a4d971350c7e5875 | 待定/待定/待定 | doc-5149b57efb060e06, doc-a4d971350c7e5875 / doc-5149b57efb060e06, doc-a4d971350c7e5875 / doc-5149b57efb060e06, doc-a4d971350c7e5875 | 正向题；ok；相对向量新增0级：None |
| C06 | 无 | doc-84a31f89a1acc2f3 | doc-84a31f89a1acc2f3 | 0/待定/待定 | 无 / doc-84a31f89a1acc2f3 / doc-84a31f89a1acc2f3 | 无允许证据，不计分母；ok；相对向量新增0级：None |

## 实际差异分析

- 关键词优势：待正文审核后比较，尚不宣称优势。
- 向量优势：待正文审核后比较，尚不宣称优势。
- 融合持平/退化：待审核，或在已审核样本中未观察到。

## 候选正文审核

等级0=无关/不支持，1=主题相关但缺关键证据，2=正文直接支持。填写 support_level、reason、reviewer、human_checked（yes/no）；AI辅助需在 reviewer 明确标记并抽查。

### Q01：怎样避免不同项目安装的包互相干扰？

过滤：{}；参考原句：为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### Q02：调用模型的密钥应放在哪里，哪些地方不应该出现？

过滤：{}；参考原句：API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-84a31f89a1acc2f3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\cooking.txt /  | 家庭厨房记录<br>番茄炒蛋可以先炒鸡蛋盛出，再炒番茄，最后合炒调味。锅温和食材含水量会影响成品口感。<br>这份菜谱讨论的是烹饪步骤，不包含软件工具调用流程。做菜时所说的工具是锅铲、菜刀和量勺。<br>准备多道菜可以先整理食材，但厨房操作的先后顺序并不能解释异步网络请求的调度机制。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### Q03：多个网络请求怎样同时等待而不逐个排队？

过滤：{}；参考原句：对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-84a31f89a1acc2f3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\cooking.txt /  | 家庭厨房记录<br>番茄炒蛋可以先炒鸡蛋盛出，再炒番茄，最后合炒调味。锅温和食材含水量会影响成品口感。<br>这份菜谱讨论的是烹饪步骤，不包含软件工具调用流程。做菜时所说的工具是锅铲、菜刀和量勺。<br>准备多道菜可以先整理食材，但厨房操作的先后顺序并不能解释异步网络请求的调度机制。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### Q04：为什么工具函数执行前要验证参数？

过滤：{}；参考原句：工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-84a31f89a1acc2f3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\cooking.txt /  | 家庭厨房记录<br>番茄炒蛋可以先炒鸡蛋盛出，再炒番茄，最后合炒调味。锅温和食材含水量会影响成品口感。<br>这份菜谱讨论的是烹饪步骤，不包含软件工具调用流程。做菜时所说的工具是锅铲、菜刀和量勺。<br>准备多道菜可以先整理食材，但厨房操作的先后顺序并不能解释异步网络请求的调度机制。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### Q05：模型提出调用工具后，谁执行函数，结果怎样传回？

过滤：{}；参考原句：模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-84a31f89a1acc2f3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\cooking.txt /  | 家庭厨房记录<br>番茄炒蛋可以先炒鸡蛋盛出，再炒番茄，最后合炒调味。锅温和食材含水量会影响成品口感。<br>这份菜谱讨论的是烹饪步骤，不包含软件工具调用流程。做菜时所说的工具是锅铲、菜刀和量勺。<br>准备多道菜可以先整理食材，但厨房操作的先后顺序并不能解释异步网络请求的调度机制。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### Q06：PDF 中间有空白页，后续引用的页数该怎样记录？

过滤：{}；参考原句：Count every physical PDF page, including blank pages, when recording citations.。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-870ad51e4b6db443 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\printed_pages.md /  | # 纸质书编排说明<br>纸质书的印刷页码可能从正文开始编号，封面和目录可能不编号，也可能使用罗马数字。<br>这里的页码是排版者印在纸上的标记，讨论的是纸质出版物。某张纸上没有印刷数字，并不等于文件解析时应该忽略该页。<br>本说明没有规定 PDF 加载器如何记录物理页号，不能单独用它支持 PDF 中间空白页之后的引用坐标。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |

### Q07：怎样利用 offset 与 end_offset 找回片段原文？

过滤：{}；参考原句：offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |

### Q08：文档与查询为什么不能分别使用两种向量模型？

过滤：{}；参考原句：文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-870ad51e4b6db443 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\printed_pages.md /  | # 纸质书编排说明<br>纸质书的印刷页码可能从正文开始编号，封面和目录可能不编号，也可能使用罗马数字。<br>这里的页码是排版者印在纸上的标记，讨论的是纸质出版物。某张纸上没有印刷数字，并不等于文件解析时应该忽略该页。<br>本说明没有规定 PDF 加载器如何记录物理页号，不能单独用它支持 PDF 中间空白页之后的引用坐标。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### Q09：如何避免 Agent 一直调用工具而不结束？

过滤：{}；参考原句：Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-84a31f89a1acc2f3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\cooking.txt /  | 家庭厨房记录<br>番茄炒蛋可以先炒鸡蛋盛出，再炒番茄，最后合炒调味。锅温和食材含水量会影响成品口感。<br>这份菜谱讨论的是烹饪步骤，不包含软件工具调用流程。做菜时所说的工具是锅铲、菜刀和量勺。<br>准备多道菜可以先整理食材，但厨房操作的先后顺序并不能解释异步网络请求的调度机制。 | 待填 |  |  /  |
| doc-870ad51e4b6db443 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\printed_pages.md /  | # 纸质书编排说明<br>纸质书的印刷页码可能从正文开始编号，封面和目录可能不编号，也可能使用罗马数字。<br>这里的页码是排版者印在纸上的标记，讨论的是纸质出版物。某张纸上没有印刷数字，并不等于文件解析时应该忽略该页。<br>本说明没有规定 PDF 加载器如何记录物理页号，不能单独用它支持 PDF 中间空白页之后的引用坐标。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |

### Q10：资料没有支持结论时，研究系统应怎样处理？

过滤：{}；参考原句：资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-870ad51e4b6db443 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\printed_pages.md /  | # 纸质书编排说明<br>纸质书的印刷页码可能从正文开始编号，封面和目录可能不编号，也可能使用罗马数字。<br>这里的页码是排版者印在纸上的标记，讨论的是纸质出版物。某张纸上没有印刷数字，并不等于文件解析时应该忽略该页。<br>本说明没有规定 PDF 加载器如何记录物理页号，不能单独用它支持 PDF 中间空白页之后的引用坐标。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### N01：本资料里的公司 2027 年营收是多少？

过滤：{}；参考原句：无支持证据。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-870ad51e4b6db443 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\printed_pages.md /  | # 纸质书编排说明<br>纸质书的印刷页码可能从正文开始编号，封面和目录可能不编号，也可能使用罗马数字。<br>这里的页码是排版者印在纸上的标记，讨论的是纸质出版物。某张纸上没有印刷数字，并不等于文件解析时应该忽略该页。<br>本说明没有规定 PDF 加载器如何记录物理页号，不能单独用它支持 PDF 中间空白页之后的引用坐标。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### N02：园艺资料是否说明了数据库管理员密码？

过滤：{}；参考原句：无支持证据。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-870ad51e4b6db443 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\printed_pages.md /  | # 纸质书编排说明<br>纸质书的印刷页码可能从正文开始编号，封面和目录可能不编号，也可能使用罗马数字。<br>这里的页码是排版者印在纸上的标记，讨论的是纸质出版物。某张纸上没有印刷数字，并不等于文件解析时应该忽略该页。<br>本说明没有规定 PDF 加载器如何记录物理页号，不能单独用它支持 PDF 中间空白页之后的引用坐标。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### C01：工具返回结果为什么需要关联原 tool_call_id？

过滤：{}；参考原句：模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-84a31f89a1acc2f3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\cooking.txt /  | 家庭厨房记录<br>番茄炒蛋可以先炒鸡蛋盛出，再炒番茄，最后合炒调味。锅温和食材含水量会影响成品口感。<br>这份菜谱讨论的是烹饪步骤，不包含软件工具调用流程。做菜时所说的工具是锅铲、菜刀和量勺。<br>准备多道菜可以先整理食材，但厨房操作的先后顺序并不能解释异步网络请求的调度机制。 | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |

### C02：两个项目需要不同版本的同一个包，怎样避免冲突？

过滤：{}；参考原句：为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-21a31aa34e21153f / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\async.md /  | # 网络任务观察<br>对于多个独立的网络请求，可以创建异步任务并用 asyncio.gather 同时等待，让一个请求等待响应时其他请求继续推进。<br>如果在循环里逐个 await 每次请求，前一个请求返回后才会启动下一个，就仍然是顺序等待。<br>异步并发适用于 I/O 等待，不意味着 CPU 计算会自动并行。实际调用还应限制并发数量，并明确超时和单个任务失败的处理策略。 | 待填 |  |  /  |
| doc-47de7bf8c30cf985 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\tools.md /  | # 执行器接口约定<br>工具执行前应按照参数 Schema 检查必填字段、类型和取值范围，避免缺失或非法参数进入业务函数。<br>参数合法不等于操作获准，执行器仍需检查权限和业务边界。<br>模型只提出工具名称和参数；应用执行器调用实际函数，再把结果封装为关联原 tool_call_id 的工具消息传回模型。<br>不能把模型提出的调用请求当成已经执行成功，也不能把不同工具的结果关联到同一个错误的调用 ID。 | 待填 |  |  /  |
| doc-67e8db8df1d1d15d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\environment.txt /  | 项目实验记录<br>为每个项目创建独立的虚拟环境，可以隔离依赖包及其版本。<br>运行脚本和安装包时应选择同一个环境中的 Python 解释器。可以使用 python -m pip 安装依赖，减少 pip 指向另一个解释器的风险。<br>虚拟环境隔离软件依赖，不会自动隔离文件、网络或操作系统权限。复制项目时保留依赖清单，通常不复制整个环境目录。 | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |
| doc-eccf50f58a9a4d9d / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\agent_control.md /  | # 循环运行手册<br>Agent 应设置最大执行步数，并在模型给出最终回答、任务取消或发生不可恢复错误时停止，避免持续调用工具而不结束。<br>工具重复失败时需要受控的失败处理，不能无限重试。达到步数上限后应报告停止原因，而不是假装任务已经完成。<br>模型请求工具只是循环的一次状态转换，应用仍负责计数、执行和检查退出条件。 | 待填 |  |  /  |
| doc-f69a71b5b9f84c38 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\embeddings.md /  | # 检索实验配置<br>文档与查询必须使用同一套向量模型和兼容的编码配置；不同模型即使输出维度相同，其坐标含义也可能不同，不能直接比较这些向量。<br>归一化、模型快照和查询指令都应记录在实验配置中。查询指令如需使用，只加在问题端，并统一重跑评测。<br>Embedding 负责生成文本的向量表示，余弦负责比较向量方向。高相似度不保证事实正确，也不能自动识别所有否定关系。 | 待填 |  |  /  |

### C03：PDF 中间有空白页时，后续引用页数应该怎样记录？

过滤：{}；参考原句：Count every physical PDF page, including blank pages, when recording citations.。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-1d7abc3ef0be35c3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\gardening.md /  | # 阳台种植笔记<br>罗勒适合放在光照充足、排水良好的位置。浇水前观察表层土壤，避免盆底长期积水。<br>种植记录包括播种日期、叶片状态、浇水次数和施肥情况。这些是植物养护信息。<br>给不同花盆贴标签有助于追踪品种，但花盆标签不具有软件依赖隔离的功能。本资料不记录任何数据库账号或密码。 | 待填 |  |  /  |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-76ab5ce75e586d60 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\offset.md /  | # 文本位置记录<br>offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。<br>文本文件以规范化整篇原文为坐标基准；PDF 片段以规范化的对应物理页文本为基准。坐标既不是 UTF-8 字节偏移，也不是 token 下标。<br>重新切片应从原始文档开始，并重新生成坐标和 ID。旧片段再次切碎后不能直接沿用原来的 offset。 | 待填 |  |  /  |
| doc-870ad51e4b6db443 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\printed_pages.md /  | # 纸质书编排说明<br>纸质书的印刷页码可能从正文开始编号，封面和目录可能不编号，也可能使用罗马数字。<br>这里的页码是排版者印在纸上的标记，讨论的是纸质出版物。某张纸上没有印刷数字，并不等于文件解析时应该忽略该页。<br>本说明没有规定 PDF 加载器如何记录物理页号，不能单独用它支持 PDF 中间空白页之后的引用坐标。 | 待填 |  |  /  |
| doc-8ed6ac9b3a883cfc / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\evidence.md /  | # 研究记录准则<br>资料不足以支持结论时，应明确说明证据不足、列出缺失信息，并在必要时继续检索；不能编造事实或用无关引用冒充证据。<br>找到主题相近的片段只是候选检索成功。回答前还要核对原句是否支持具体结论，以及来源是否适用。<br>如果只能支持问题的一部分，可以回答已证实的部分并标明其余部分未知。检索分数不是结论正确的概率。 | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |
| doc-c5b5b52aa10f6be7 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\security.md /  | # 配置交接备忘<br>API 密钥应保存在环境变量或受控的密钥存储中，不应写入源代码、提交到 Git，也不应出现在日志和聊天记录里。<br>本地使用 .env 时必须将其加入版本控制忽略规则；示例文件只能保留变量名和占位值。<br>一旦密钥泄露，应撤销并替换该密钥，而不能只删除最新一次提交里的字符串。日志可以记录请求是否成功，但不要输出完整凭据。 | 待填 |  |  /  |

### C04：PDF 中间有空白页时，后续引用页数应该怎样记录？

过滤：{'file_types': ['pdf']}；参考原句：Count every physical PDF page, including blank pages, when recording citations.。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |

### C05：PDF 中间有空白页时，后续引用页数应该怎样记录？

过滤：{'relative_paths': ['document_tracking.pdf']}；参考原句：Count every physical PDF page, including blank pages, when recording citations.。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-5149b57efb060e06 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 1 | Document tracking notes<br>This fixture contains three physical PDF pages.<br>The second physical page is intentionally blank.<br>Page labels printed on a page may differ from its physical position. | 待填 |  |  /  |
| doc-a4d971350c7e5875 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\document_tracking.pdf / 3 | Citation coordinates<br>Count every physical PDF page, including blank pages, when recording citations.<br>This text is on physical page 3, even though page 2 has no extracted text.<br>Do not renumber later pages after skipping a blank page during extraction. | 待填 |  |  /  |

### C06：怎样利用 offset 和 end_offset 找回原文？

过滤：{'relative_paths': ['cooking.txt']}；参考原句：offset 和 end_offset 是规范化文本中的字符坐标，用 normalized_text[offset:end_offset] 可以还原对应片段，end_offset 不包含在范围内。。

| ID / 文件 / 页 | 候选正文 | 等级 | 理由 | 审核者 / 人工抽查 |
| --- | --- | --- | --- | --- |
| doc-84a31f89a1acc2f3 / E:\agent_project\agent-learning-lab\data\day08\retrieval-v1\corpus\cooking.txt /  | 家庭厨房记录<br>番茄炒蛋可以先炒鸡蛋盛出，再炒番茄，最后合炒调味。锅温和食材含水量会影响成品口感。<br>这份菜谱讨论的是烹饪步骤，不包含软件工具调用流程。做菜时所说的工具是锅铲、菜刀和量勺。<br>准备多道菜可以先整理食材，但厨房操作的先后顺序并不能解释异步网络请求的调度机制。 | 待填 |  |  /  |

## 成本和边界

模型加载、建库、预热单列于 raw_results.json 的 startup；逐题 search_ms 是热搜索时间，candidate_result 的 elapsed_ms 含来源一致性检查。RRF成本计两路搜索加融合，context_ms单列。

候选重复率按每题融合前两路原始候选计算后汇总（不是跨问题去重）。跨路重合可提供有用信号。详见 summary.json 的分子、分母与统计范围。

无差异的机制解释可独立运行 day09_fusion.py --demo；合成例子不能替代本次真实成绩。
