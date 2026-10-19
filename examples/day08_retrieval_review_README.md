# 阶段八：Top-3 检索与人工审核

## 生成初始结果

在项目根目录运行（PyCharm 直接运行无须参数）：

```powershell
.\.venv\Scripts\python.exe examples\day08_evaluate_retrieval.py
```

默认读取阶段七的 data/day08/retrieval-v1，固定实际模型快照、依赖版本、400/60 切片、归一化及无查询指令。
会先核验文件哈希、证据句和派生 Source ID，再编码一次全部文档，分别查询 10 道正向题及 2 道探针。
新增、删除或修改资料、移动语料目录、更换配置导致标签过期时明确报错，先准备新的数据版本。

每次运行使用独立的时间戳目录和 Chroma 库，路径会打印在控制台：

```text
data/day08/retrieval-evaluation/<run-id>/
  raw_results.json     原始问题、标签、Top-3 正文、排名、ID、来源、页码、distance、score
  raw_integrity.json   原始结果校验值，report 时检查是否被意外改动
  dataset_manifest.json 固定模型、语料、切片配置的副本
  length_audit.json    本次运行实际长度审计
  review.csv          UTF-8 BOM 人工审核表，每个候选一行
  review.md           完整正文与预标注证据的 Markdown 阅读版
  summary.json        当前审核进度与指标
  reports/            每次 report 的计分结果及审核表快照
  chroma/             本次实验专用向量库
```

## 人工填写

打开 review.md 对照正文，在 review.csv 中只填写以下三列：

- support_level：0=无关或不支持；1=主题相关但缺关键证据；2=正文直接支持题目要点。
- reason：每条已评分候选必须填理由，说明正文具体支持或缺少什么。
- error_cause：需要时记录漏检、相似干扰、跨语言等原因；支持正确的候选可留空。

不要仅因文件名正确或 score 高就填 2。不要修改候选正文、排名、ID、标签等其他列，也不能删行。
Excel 等软件保存 CSV 时选择 UTF-8 并保留原始数字字符串格式，避免距离/分数或长文本被重写。
preannotated_evidence_match 仅表示事先标注的完整证据片段 ID 命中，不代替人工判定。
N01/N02 也需检查候选；N02 的“无目标答案”指没有可给出的真实密码，不是忽略文档关于不记录密码的说明。

## 计算人工 Hit@3

将下面路径替换为控制台打印的具体运行目录：

```powershell
.\.venv\Scripts\python.exe examples\day08_evaluate_retrieval.py report --run-dir "data/day08/retrieval-evaluation/<run-id>"
```

report 不调用模型、不重跑检索，只校验并读取审核表。
10 道正向题的全部 30 条候选填写完整后，才计算人工 Hit@3 = 存在等级 2 候选的正向题数 / 10。
没填完时 manual_hit_at_3 为 null，不能使用部分已审题目缩小分母；待填行数同时包含探针行。
N01/N02 不计入分母，单独在 per_query 中显示人工结果。自动预标注 ID 命中率与人工指标分开保存。
当前标签每题只有一条必要关键句，因此不另造多证据覆盖指标。Hit@3 不是 Recall@3 或回答准确率。

## 保留初始与修正结果

重新运行 run 会创建新目录，不覆盖初始分数。修正实验应记录原因，例如：

```powershell
.\.venv\Scripts\python.exe examples\day08_evaluate_retrieval.py run --dataset-root "data/day08/retrieval-v2" --note "v2：调整切片边界，保留原10题和证据标签"
```

对照实验请比较不同运行的 summary.json，不删失败题、不按结果改正确标签。
先检查加载、截断、模型一致性、距离排序和干扰，再考虑查询指令实验。
当前脚本只支持无查询指令基线，不会混合不同问题预处理规则。10 题上的反复优化可能过拟合，不代表生产系统质量。
