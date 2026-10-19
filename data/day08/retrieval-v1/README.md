# Day 08 固定检索语料 v1

此数据集包含 12 份合成资料：11 份 TXT/Markdown 和 1 份文本型 PDF。
正文是教学实验约定，不包含真实组织财务数据或真实凭据。
questions.jsonl 是检索前编写并确认的 Q01～Q10 人工标签，不根据模型排名修改。
probes.jsonl 是 N01、N02 两个无目标答案探针，不计入正向命中率分母。
无证据探针需要人工检查候选是否支持目标答案，不承诺固定阈值能自动拒答。
N02 的“无证据”指语料没有可给出的数据库管理员密码；园艺文档中关于不记录密码的否定说明不构成密码答案。

## 运行

在项目根目录运行，PyCharm 直接运行脚本也不需要参数：

```powershell
.\.venv\Scripts\python.exe examples\day08_prepare_retrieval_dataset.py
```

要求已安装项目 vector 扩展和 BGE 模型。默认使用 CPU、400/60 字符切片及统一归一化规则。
脚本加载 SentenceTransformer 做实际 token 长度审计，但此阶段不编码文档向量、不写入 Chroma、不执行检索。
问题端审计包含 Q01～Q10、N01～N02 和特殊 token。当前基线不加查询指令。

## 生成文件

- sources.jsonl：加载器生成的完整 Source 快照。
- resolved_labels.json：原人工标签、完整关键句匹配规则和 acceptable_source_ids。
- length_audit.json：每个片段和问题的 token 数以及超长数量。
- dataset_manifest.json：文件 SHA256、数据指纹、切片参数、实际模型快照和依赖版本。

ID 由路径、片段位置与内容共同决定。迁移到另一台机器或移动目录后需重跑脚本，不能继续使用旧的派生 ID。
相同输入和配置可重复准备；改变语料、切片参数或模型配置时应创建新版本目录，通过 --dataset-root 指定。

## 证据规则

必须同时匹配 relative_path、物理页号和完整关键句；文本文件页号为 null。
overlap 导致多个片段完整包含关键句时，所有命中片段均为 acceptable_source_ids。
关键句跨片段或标注缺失时明确报错；本基线只使用单片段足以支持结论的证据，不猜测片段组合。
Q04 与 Q05 共享工具资料，分别检验参数校验原因和工具消息流程，文件与问题不是一一配对。
无关资料包含烹饪、园艺；近似干扰资料讨论纸质书印刷页码，不能代替 PDF 物理页码证据。

## PDF 特例

document_tracking.pdf 共 3 个物理页，第 2 页完全空白；加载器保留第 1、3 页，并报告第 2 页警告。
Q06 标注第 3 页英文证据，额外包含中文问题检索英文正文的因素；后续应单独观察该题，不把跨语言失败直接等同于页码错误。
PDF 以 Helvetica 生成，避免字体问题扩大为 OCR；用 scripts/generate_day08_retrieval_pdf.py 可复现原件（需要 reportlab）。
生成器拒绝覆盖已存在的 PDF。实际 corpus 文件已提供，无需再次运行生成器。
