# Day 07：本地文档加载、来源追溯与 PDF 页码——PyCharm 详细学习计划

> 项目：`E:\agent_project\agent-learning-lab`  
> 环境：PyCharm + 项目 `.venv` 中的 Python 3.11  
> 学习投入：当天总计 8 小时，各阶段弹性安排  
> 主线：读取文件 → 解析文本 → 保留文档/页级信息 → 切片 → 统一 Source → 单独记录失败

## 1. 对齐六周项目计划总览

本计划依据你此前提供的六周总览中“第 7 天：本地文档加载”，并与项目 `curriculum/week-02.md` 的 Day 7 条目对齐。

| 总览要求 | 今天的具体交付 |
|---|---|
| 加载 TXT、Markdown、PDF | 三种合成文件进入同一个 load_document 入口 |
| 统一文档表示 | 复用项目已有 Source，明确每个对象代表一个文本片段 |
| 保留文件名、页码、标题、来源 | 字段映射表、元数据断言、人工回到原文件验证 |
| 区分解析失败、空文件、扫描型 PDF | 明确错误类别与“疑似扫描件/无文本层”提示 |
| 支持三类文件进入统一流程 | 一次混合目录实验，成功内容与失败记录分别保留 |
| 扩展 DOCX、内容哈希 | 核心验收完成后再选择，不阻塞今天 |

总览中的 Document 是“统一文档对象”的概念。当前项目已经用 Source 同时承载网页正文和本地片段，今天继续使用它。不要为名称一致再造一套字段几乎相同的 Document 类。

## 2. 今天为什么重要

Day 06 的网页链路把 HTML 转成可追溯的正文。今天把磁盘上的文件转成同样可处理的资料。

后续 Agent 回答“这个结论来自哪个文件、第几页”时，依赖今天保存的元数据。如果加载时就丢掉文件路径或页码，后面再让模型补充来源，很容易得到猜测。

从工程角度，本课最重要的四件事是：

1. **解析边界明确：**读取字节、解释文件格式、清洗文本、切片是不同步骤。
2. **来源信息随内容传递：**每个 chunk 都能回到文件；PDF 还能回到物理页。
3. **失败可以观察：**坏文件不拖垮整批，也不能被无声忽略后当作全部成功。
4. **验证依靠固定资料：**使用自建小样例和真实解析器，结果可重复、无需网络。

今天不需要模型调用、Embedding 或向量数据库。先把送入检索的数据准备正确，Day 08 再学习向量化和索引。

## 3. 弹性学习规则与今日成果

每个阶段按“先预测 → 操作 → 观察 → 解释 → 测试”推进。总投入 8 小时，不规定各项分别占几个小时。

- 核心任务没有通过检查点，就先缩小问题、保住最小版本。
- 有余力再做 DOCX、哈希去重、复杂 PDF 排版。
- 未完成核心项记入日志，下一次先补，不能靠删验收项收尾。

今日必须交付：

- [ ] 一张 TXT/Markdown/PDF 到 Source 的流程图。
- [ ] TXT、Markdown、两页文本 PDF 的统一 Source 示例。
- [ ] 正确的物理页码、文件路径和可解释的字符 offset。
- [ ] 空文本、坏编码、损坏 PDF、无文本 PDF 的明确结果。
- [ ] 混合目录加载：成功片段、文件级失败、页级警告分别可查看。
- [ ] 不依赖网络和模型的行为测试。
- [ ] PyCharm 演示、学习日志和 Git 提交。

## 4. 与现有进度衔接

2026-10-12 阅读当前项目得到：

- Day 06 日志已记录网页纯解析、URL 去重、元数据、批处理与离线测试的实现。
- documents.py 已支持 .txt、.md、.markdown、.pdf。
- TXT/Markdown 用 utf-8-sig 读取，随后直接切片。
- PDF 用 PyMuPDF 逐页取文本，page 使用从 1 开始的编号。
- `_chunk_sources()` 已有默认 chunk_size=900、overlap=120，并尝试在句号或换行处断开。
- metadata 目前只有 offset；它对应清洗后的文本，不是原文件字节位置。
- load_all_documents() 会跳过 DocumentLoadError，不返回失败清单。
- 文本解码、文件读取、损坏 PDF 等异常还没有全部转换为统一的文档错误。
- 现有 tests/test_documents.py 只有文本来源、空文件、路径边界几类基础测试。

这些是今天的起点，不是完整验收已经完成。你修改过的部分以当前代码为准，先阅读再补缺口。

## 5. 文件操作清单

以下路径相对于项目根目录。

| 文件 | 操作 | 重点 |
|---|---|---|
| `src/research_agent/documents.py` | 核心修改 | 加载、页码、清洗、切片、错误与批次诊断 |
| `src/research_agent/models.py` | 阅读为主 | Source 字段，不随意改变公共接口 |
| `src/research_agent/config.py` | 阅读 | document_root 与工作目录 |
| `src/research_agent/runtime.py` | 只读对照 | 加载结果怎样进入索引 |
| `src/research_agent/api.py` | 只读对照 | 上传入口如何使用 DocumentLoadError |
| `tests/test_documents.py` | 扩充 | 三种格式、错误、页码、offset、批处理 |
| `tests/fixtures/day07/notes.txt` | 新建 | UTF-8 中文 TXT 合成资料 |
| `tests/fixtures/day07/guide.md` | 新建 | 含标题、列表、代码块的 Markdown |
| `examples/day07_make_samples.py` | 新建 | 生成小型 PDF 和异常样例 |
| `examples/day07_document_lab.py` | 新建 | 单文件与混合目录演示 |
| `curriculum/day-07-log.md` | 新建 | 字段表、测试、人工验证和局限 |
| `.gitignore` | 按需追加 | 忽略 data/day07/ 运行样例与输出 |

PDF 可以在 pytest 的 tmp_path 内由 PyMuPDF 动态生成，避免依赖网上下载的未知文档。手写 TXT/Markdown fixtures 和样例生成脚本应进入 Git；运行生成物按本课约定忽略。

## 6. 阶段零：确认环境与原有契约

### 6.1 检查依赖

在 PyCharm Terminal 执行：

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import fitz; print('PyMuPDF:', fitz.VersionBind)"
.\.venv\Scripts\python.exe -m pytest tests/test_documents.py -q
```

项目依赖已包含 pymupdf。`fitz` 是当前实现使用的导入名，不要额外安装一个叫 fitz 的无关包。导入成功就继续，不需要升级全部环境。

记录真实测试结果，不预填通过数量。

### 6.2 阅读调用链

按顺序打开：

```text
safe_document_path()
→ load_document()
→ TXT/Markdown 分支 或 _load_pdf()
→ _chunk_sources()
→ load_all_documents()
```

在日志写出职责：

| 环节 | 输入 | 输出 |
|---|---|---|
| 路径检查 | root、候选 path | 允许目录内的解析后绝对路径 |
| 文件解析 | 字节文件 | 整篇文本或逐页文本 |
| 文本清洗 | 提取后的文本 | 明确规则的规范化文本 |
| 切片 | 文本与来源信息 | 多个 Source |
| 批处理 | 目录 | 成功来源、失败记录、警告 |

load_document 返回 list[Source]，因为一个文件可能包含多页、多片。文件数量、页面数量、chunk 数量不能混用。

**检查点：**能指出哪里读取磁盘，哪里开始切片，哪里生成 source_id。

## 7. 阶段一：明确统一文档契约

### 7.1 今天的 Source 表示什么

本地 Source 代表“来自某个文件、可选某页的一段可检索文本”。文件级信息复制到每片，页级信息来自对应页面。

| 字段 | 今日约定 |
|---|---|
| source_id | 当前片段的 ID，沿用 doc- 前缀 |
| title | 可读名称；TXT/Markdown 至少保留文件名，PDF 可加“第 N 页” |
| content | 本片段的文本，非空 |
| file_path | 文件解析后的绝对路径 |
| url | 本地文件为 None |
| page | PDF 物理页码从 1 开始；TXT/Markdown 为 None |
| fetched_at | 本次加载/创建附近的时间，不是文件作者写作时间 |
| metadata.content_kind | `local_document`，与 Day 06 的网页类型区分 |
| metadata.file_name | 文件名，包含扩展名 |
| metadata.relative_path | 相对于允许根目录的路径，便于展示 |
| metadata.file_type | txt、markdown 或 pdf |
| metadata.chunk_index | 本文规定为同一文本单元内从 0 开始；PDF 每页重新计数 |
| metadata.offset | 本片段在规范化文本中的字符起点 |
| metadata.end_offset | 对应字符终点，不包含该位置 |
| metadata.offset_basis | `normalized_document_text` 或 `normalized_page_text` |

新 metadata 字段是今天建议补充的契约，当前实现尚未全部提供。

### 7.2 标题与文件名不要混淆

核心要求先确保文件名不丢。Markdown 可以继续将文件名作为 Source.title，另外把首个一级标题放入 metadata.display_title 作为扩展；没有标题时正常回退。

不需要今天接入 Markdown 渲染器。保留 Markdown 文本结构，让标题、列表、代码块内容能进入后续检索。

### 7.3 文档身份与片段身份

当前 source_id 的输入包含路径、页码、起点和内容，所以它代表片段。移动文件或改变切片规则可能改变片段 ID。不能据此声称跨电脑、跨版本永远稳定。

内容哈希去重放在扩展，先完成正确的来源映射。若增加 document_id，必须单独说明它代表路径身份还是内容版本，不能和 chunk ID 混用。

**检查点：**拿任意一个 Source，能找到文件；PDF 能找到对应物理页；能解释 offset 的参照物。

## 8. 阶段二：TXT 与 Markdown 加载

### 8.1 创建可控资料

notes.txt 写入 UTF-8 中文文本，例如：

```text
Agent 使用模型理解问题，并由程序组织工具调用。
工具执行前需要检查参数。
来源信息应在文档处理过程中保留。
```

guide.md 至少包含：

````markdown
# Agent 学习笔记

## 文档来源

- 文件路径用于回到原文件。
- PDF 页码用于定位具体页面。

```python
print("保留代码块里的文本")
```
````

### 8.2 在 PyCharm 中直接加载

先在 day07_document_lab.py 中做最小调用：

```python
from pathlib import Path

from research_agent.documents import load_document

root = Path("tests/fixtures/day07").resolve()
for name in ("notes.txt", "guide.md"):
    sources = load_document(root / name, root)
    print(name, "chunks:", len(sources))
    for source in sources:
        print(source.title, source.page, source.metadata)
        print(source.content)
```

确认工作目录为项目根目录。

### 8.3 建立编码与空文本规则

沿用 utf-8-sig：普通 UTF-8 可以读取，开头有 BOM 的文件也能处理。

- 0 字节文件：明确 empty_document。
- 只有空格、换行：同样是无可用文本。
- 非 UTF-8 编码：明确 encoding_error，说明当前支持范围。
- 不使用 `errors="ignore"` 静默丢掉中文。
- 暂不自动猜编码；显式 GB18030 等兼容策略作为扩展。

文本清洗先复用现有规则并写清楚：每行 strip，去掉空行，再用换行连接。它可能改变 Markdown 缩进和代码格式。今天保证文本可检索，并记录这一限制；若要保存完整代码排版，应另行设计，而不是声称原样保留。

**检查点：**TXT/Markdown 都进入 list[Source]；中文与核心内容保留；坏编码与空文本是不同结果。

## 9. 阶段三：逐页解析 PDF

### 9.1 生成两页文本 PDF

创建 examples/day07_make_samples.py，先加入：

```python
from pathlib import Path

import fitz

out_dir = Path("data/day07/input")
out_dir.mkdir(parents=True, exist_ok=True)

with fitz.open() as doc:
    for marker in ("PAGE_ONE: tools and parameters", "PAGE_TWO: sources and citations"):
        page = doc.new_page()
        page.insert_text((72, 72), marker)
    doc.save(out_dir / "two_pages.pdf")
```

固定 PDF fixture 先用英文标记，避免字体嵌入与中文显示问题干扰页码练习。TXT/Markdown 仍验证中文；有现成中文文本 PDF 时再补人工观察。

程序生成页面后，要实际提取文本验证标记存在。生成文件成功不代表文字确实进入可提取文本层。

### 9.2 观察 PyMuPDF 的页索引

```python
with fitz.open("data/day07/input/two_pages.pdf") as doc:
    for index, page in enumerate(doc):
        print("内部索引:", index, "展示页码:", index + 1)
        print(page.get_text("text"))
```

load_document 应返回 page=1 和 page=2 的片段。PAGE_ONE 不能出现在 page=2 的片段里，反之亦然。

先逐页提取并带上 page，再按页切片。不要先拼接全文，再试图根据 chunk 编号推算页码。

本文 page 指 PDF 物理页序号，不是印在页面上的编号，也不是目录中显示的逻辑页标签。封面可能没有印页码，但物理上仍是第 1 页。

### 9.3 文本提取的局限

PyMuPDF 可以提取文本，但默认输出的阅读顺序可能受 PDF 内部布局影响。双栏、表格、页眉页脚不能只用“提取了字符串”判定质量。参见 [PyMuPDF 文本提取说明](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)。

核心验证使用简单页面；复杂排版观察与 sort/blocks 策略作为扩展，不把它们塞进今天的最小加载器。

**检查点：**每片 PDF 文本都携带原始物理页码，单片不跨页。

## 10. 阶段四：区分空白页、疑似扫描件和损坏 PDF

### 10.1 需要区分的情况

| 情况 | 解析现象 | 今日处理 |
|---|---|---|
| 正常文本 PDF | 打开成功、提取到文本 | 返回逐页 Source |
| 混合 PDF | 部分页有文本，部分为空 | 保留有文本页，记录空文本页警告 |
| 全部页面无文本 | 打开成功，每页提取为空 | no_extractable_text，提示“可能是扫描件或无文本层” |
| 真正空白 PDF | 页面可打开，但无文字和图片 | 同属无可提取文本，不能肯定说是扫描件 |
| 损坏或伪 PDF | 打开/读取失败 | parse_error |
| 需密码的 PDF | needs_pass 为真 | password_required，不尝试猜密码 |
| 0 字节 .pdf | 没有有效文件内容 | empty_document 或明确的空 PDF 错误 |

仅凭 get_text() 为空，不能确定“这是扫描件”。它也可能是空白页、轮廓文字或其他没有可提取文本的布局。

### 10.2 生成疑似扫描件 fixture

用刚才生成的文本页渲染成 Pixmap，然后将图片插入一个全新的 PDF 页面，只保存图片，不添加文字层。

建议实现顺序：

```text
打开 two_pages.pdf
→ 对一页 get_pixmap()
→ 新建 PDF
→ new_page()
→ insert_image(..., pixmap=...)
→ 保存 image_only.pdf
```

生成后同时检查：该页能渲染为图像，但 get_text("text").strip() 为空。不要用“没有创建任何内容的空白页”代替扫描样例。

### 10.3 混合页实验

生成三页 PDF：第 1 页有文本，第 2 页空白或只有图片，第 3 页有文本。

预期：片段页码是 1 和 3，而不是 1 和 2。metadata 中可保存 empty_pages=[2]；批次报告汇总一条警告，说明第 2 页未提取到文本，不能将整份文档标成“全部页面已解析”。

今天选择继续保留其余页，不默认启用 OCR。OCR 需要独立依赖、语言与质量评估，放在后续扩展。

### 10.4 错误统一在文件解析边界

在 documents.py 中将预期文件错误转换为 DocumentLoadError，保留异常链：

```python
raise DocumentLoadError("文档解析失败：请检查文件是否损坏") from exc
```

建议给错误增加可选 code 属性，保留原有字符串消息与类型兼容性，例如 encoding_error、parse_error、empty_document、no_extractable_text、password_required、outside_root、not_found、unsupported_type。

捕获范围围绕实际读取/解析语句，区分 UnicodeDecodeError、OSError 与 PyMuPDF 的相关异常。不要用覆盖整个程序的 except Exception 隐藏切片算法或开发断言错误。

资源通过 with 管理，即使提取失败也关闭 PDF。加密状态与相关异常类型可对照 [PyMuPDF Document API](https://pymupdf.readthedocs.io/en/latest/document.html)，并核对本地安装版本。

**检查点：**无文本 PDF、损坏 PDF、坏编码 TXT 得到可区分的反馈；第 3 页不会因第 2 页跳过而改号。

## 11. 阶段五：让 chunk 与 offset 可验证

本课只把现有切片器的契约理顺。不同 chunk 参数的检索效果比较留给 Day 08。

### 11.1 先明确坐标系

当前清洗逻辑删除空行、去掉每行首尾空白，因此 offset 指向清洗后的字符串。

```text
TXT/Markdown：规范化后的整篇文本，从 0 开始的字符位置
PDF：该物理页规范化后的文本，从 0 开始的字符位置
```

不是 UTF-8 字节偏移，不是编辑器里的原始行列，不是 PDF 屏幕坐标。中文字符在 Python 字符串索引中也不按 UTF-8 字节长度计算。

建议提取 normalize_document_text(text) 纯函数，让切片与测试使用同一明确规则。对 Markdown 的格式损失写入已知限制。

### 11.2 当前实现有一个需要验证的边界

_chunk_sources 使用 normalized[start:end].strip() 作为 content，但 metadata.offset 仍保存 start。如果切片恰好从空格或换行处开始，strip 删除了前缀，保存的起点可能与 content 不完全对应。

先用含内部空格和换行的短文本、很小的 chunk_size 重现，再修正：

```python
raw = normalized[start:end]
content = raw.strip()
left_trim = len(raw) - len(raw.lstrip())
content_start = start + left_trim
content_end = content_start + len(content)
```

非空片段保存 offset=content_start、end_offset=content_end。下一片推进仍依据原切片 end/overlap，不要因展示内容被裁剪而倒退或重复。

每片必须通过：

```python
assert normalized[source.metadata["offset"]:source.metadata["end_offset"]] == source.content
```

PDF 测试要用对应页的 normalized，而不是整份 PDF 拼接后的文本。

### 11.3 参数边界与终止

- chunk_size 必须为正整数。
- overlap 必须为非负整数且严格小于 chunk_size。
- 非法参数在进入 while 前拒绝。
- 切片起点持续前进，没有无限循环。
- 空规范化文本不创建空 Source。
- 不跨 PDF 页切片。

### 11.4 最小实验

用没有句号与换行的短字符串，例如 `ABCDEFGHIJKLMNO`，设置 chunk_size=6、overlap=2，先手算片段，再运行比对。

另用含句号的中文文本观察边界调整。真实切片长度与重叠长度会受断句、空白裁剪影响，不要将所有输入都断言为精确等长。

保留目前默认 900/120 即可；它们只是字符数量，不等于模型 Token。今天不寻找“通用最佳 chunk 参数”。

**检查点：**给出一个 Source，能从规范化文本按 offset/end_offset 截出完全相同的 content。

## 12. 阶段六：保留路径边界与元数据

### 12.1 允许目录与候选路径

当前 safe_document_path 会 resolve root 与 candidate，再检查 candidate 是否位于 root 内。Path 的解析与相对路径操作可参考 [Python 3.11 pathlib 文档](https://docs.python.org/3.11/library/pathlib.html)。

本课调用方式统一为：

```python
root = Path("data/day07/input").resolve()
path = root / "two_pages.pdf"
sources = load_document(path, root)
```

当前实现中，单独传 Path("two_pages.pdf") 会相对进程工作目录解析，并不会自动拼到 root 下。要么明确调用约定，要么另设计接收相对文档名的接口；不要靠猜路径通过测试。

### 12.2 要验证的边界

- 允许根目录内的正常文件能够加载。
- `../` 逃出根目录时拒绝。
- 同前缀的兄弟目录不能通过，例如 docs 与 docs-other。
- 路径不存在、路径是目录、文件类型不支持时分别报错。
- 在系统允许创建符号链接的环境，可扩展验证链接解析到目录外时拒绝；Windows 无权限创建时记录跳过原因。

今天保留现有路径检查即可，不开发通用文件权限系统。

### 12.3 元数据在切片前建立

在 load_document 得到规范路径与类型后，建立文件名、relative_path、file_type、content_kind；在 PDF 循环中加 page 和页级警告。传入切片器后，为每个 Source 复制这些信息，再加 chunk_index、offset、end_offset。

不要先产生一堆没有来源的字符串，再根据列表位置猜测文件与页码。也不要让不同片段共享同一个会被继续修改的 metadata 字典。

**检查点：**同一 PDF 第 3 页的所有片段都保留 page=3，修改一个片段的 metadata 不影响其他片段。

## 13. 阶段七：混合目录批处理与诊断

### 13.1 为什么当前批处理需要补充

目前 load_all_documents 跳过 DocumentLoadError，调用方只能拿到成功片段。空文件和扫描 PDF 可能被静默忽略；某些还未包装的解码/解析异常又可能中断整批。

沿用 Day 06 的思路：单项失败独立记录，成功资料继续保留。

### 13.2 建议新增详细入口

在 documents.py 中新增 load_all_documents_detailed(root)，返回结构例如：

```text
sources：list[Source]
errors：文件级失败记录
warnings：页级/部分加载提醒
loaded_files：成功产生资料的文件数
failed_files：失败的受支持文件数
skipped_files：因类型不支持而未尝试的文件数
```

可用一个小的 Pydantic 结果模型或 dataclass 实现，不要求引入新的框架。列表默认值要独立创建。

失败记录建议包含 relative_path、error_code、简短 message；混合 PDF 警告包含 relative_path、page 和 no_text_on_page。避免把整份敏感文档内容写入错误日志。

### 13.3 兼容现有使用者

load_all_documents(root) 继续返回 list[Source]，可以委托详细入口后返回 sources。runtime.py、MCP 等旧调用无需当天改成新返回类型。

需要看错误报告的 Day 07 演示显式调用详细入口。旧入口只返回成功来源的事实写清楚，不宣称所有调用方已经能看见诊断。

目录创建策略也要明确：现有旧入口会创建 root。建议详细入口用于读取已有目录，不存在时明确报错；旧入口如要保持兼容，可在委托前保留创建动作。不要让路径拼错默默变成一个新空目录，却报告“没有文档”。

### 13.4 固定目录实验

准备以下 9 个文件：

| 文件 | 预期 |
|---|---|
| notes.txt | 成功 |
| guide.md | 成功 |
| two_pages.pdf | 成功，两页来源 |
| mixed.pdf | 部分页面成功，一条或多条页警告 |
| empty.txt | 文件失败 |
| bad_encoding.txt | 文件失败 |
| broken.pdf | 文件失败 |
| image_only.pdf | 文件失败，无可提取文本提示 |
| ignored.bin | 跳过类型，计入 skipped_files |

按这组固定输入，预期文件级统计是：loaded_files=4、failed_files=4、skipped_files=1。sources 数量由切片决定，不要求等于 4。

mixed.pdf 同时贡献成功来源和警告，不重复记成整个文件失败。扫描件失败不能污染成功 sources。

今天的批处理先串行读取小文件即可。PDF 解析是同步工作，把函数写成 async 不会自动提升吞吐量。并行读取、大文件任务隔离作为后续扩展。

**检查点：**一个坏 PDF 不阻止其余正常资料进入 Source，失败文件不会无声消失。

## 14. 阶段八：固定测试与人工质量验证

继续扩充 tests/test_documents.py。需要时拆成 test_document_pdf.py/test_document_batch.py，但无需为文件数量而拆分。

### 14.1 核心测试矩阵

| ID | 场景 | 必须证明 |
|---|---|---|
| T01 | UTF-8 中文 TXT | 中文内容保留，路径/标题/类型明确 |
| T02 | 含 BOM 的 TXT | BOM 不进入正文 |
| T03 | Markdown/.markdown | 标题、列表、代码文本进入统一流程；格式限制已知 |
| T04 | 0 字节与纯空白文本 | empty_document，无空片段 |
| T05 | 非 UTF-8 字节 | encoding_error，而非乱码或丢字后成功 |
| P01 | 两页文本 PDF | 两页标记与 page=1/2 一一对应 |
| P02 | 混合 PDF | 跳过无文本页但保留物理 page=1/3 和警告 |
| P03 | 图片型 PDF | no_extractable_text，提示疑似扫描件/无文本层 |
| P04 | 全空白 PDF | 无文本结果，不断言一定是扫描件 |
| P05 | 损坏/0 字节 PDF | 统一文档错误，不泄漏未处理解析异常 |
| P06 | 需密码的 PDF | password_required；核心可以用可控 fixture/解析对象验证 |
| C01 | offset 精确性 | 按声明坐标系切片等于 content |
| C02 | 参数边界 | 非法 size/overlap 立即失败，合法循环会终止 |
| C03 | 元数据独立 | 每片都有来源，修改一片不污染另一片 |
| B01 | 混合目录 | 成功、失败、警告、跳过数符合约定 |
| S01 | 根目录边界 | 越界、兄弟前缀、文件不存在/目录输入被明确处理 |

可参数化多个输入；实际 pytest 实例数可能多于上表行为数。验收依据是行为覆盖，不是凑某个通过数字。

### 14.2 测试资料的生成原则

- 测试文件通过 tmp_path 创建，固定小内容，不读用户私有目录。
- 文本 PDF 与图片 PDF 使用真实 PyMuPDF 生成，再用真实解析器读取；不要只 Mock get_text 后宣称 PDF 支持完成。
- 需密码、权限等难构造边界可以有针对性地 Mock，清楚标明验证范围。
- 路径中的临时目录每次变化，断言 root.resolve()/path.resolve()，不写死某个用户名路径。
- source_id 可检查唯一性与同环境同内容的可重复性，不断言跨电脑始终相同。
- 断言错误类别和必要字段，避免依赖 PyMuPDF 各版本完全相同的错误句子。

### 14.3 测试不是质量检查的全部

人工打开 two_pages.pdf 和 image_only.pdf 对照：

1. 正常 PDF 的标记能否复制、与提取文本一致？
2. 图片型 PDF 看得到文字，但解析器是否确实没有文本层？
3. 任意 Source 的 page 能否回到正确页面？
4. Markdown 清洗是否破坏了需要保留的信息？

再任选一份自己有权使用的短文档做人工验证，日志仅保存脱敏小片段；不把私有文件放进 fixtures 或提交 Git。

**检查点：**分清“文件能打开”“有可提取文本”“抽取质量合格”“有准确来源”四件事。

## 15. 阶段九：PyCharm 演示与断点

### 15.1 先生成样例

创建 Python 运行配置：

| 配置项 | 值 |
|---|---|
| 名称 | `Day07 Make Samples` |
| 脚本 | `E:\agent_project\agent-learning-lab\examples\day07_make_samples.py` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | `E:\agent_project\agent-learning-lab\.venv\Scripts\python.exe` |

生成器应把手写 TXT/Markdown fixtures 复制到 data/day07/input，再生成上述 PDF/异常样例；只操作这个专用实验目录，不递归删除其他资料。

重复运行时明确覆盖同名合成文件或提示已存在，不能混入以前实验的随机文件后仍断言固定数量。

### 15.2 再运行文档实验

第二个配置：

| 配置项 | 值 |
|---|---|
| 名称 | `Day07 Document Lab` |
| 脚本 | `E:\agent_project\agent-learning-lab\examples\day07_document_lab.py` |
| 工作目录 | `E:\agent_project\agent-learning-lab` |
| 解释器 | 项目 `.venv` |

演示脚本完成：

```text
显示本次允许根目录
→ 分别加载 TXT、Markdown、两页 PDF
→ 展示每片的文件名、page、offset、长度和少量预览
→ 加载混合目录
→ 输出成功/失败/警告统计
→ 导出脱敏的 Source 示例与诊断报告
```

输出保存在 data/day07/output，使用 Source.model_dump(mode="json") 或 model_dump_json() 处理日期字段，不把 datetime 直接交给普通 json.dumps 而忽略报错。

### 15.3 断点位置

1. safe_document_path 的 resolve 与 relative_to。
2. load_document 的扩展名分支。
3. _load_pdf 的逐页循环和无文本判断。
4. normalize_document_text 前后。
5. _chunk_sources 的 start/end 与 trim 修正。
6. 创建 Source 和批处理捕获 DocumentLoadError 的位置。

观察 path、page_number、raw_text、normalized、start、end、content、metadata。不要只看最后打印的字符串。

**检查点：**用一次正常 PDF 和一次图片 PDF，讲清两个执行路径在哪一步分开。

## 16. 回归测试与问题诊断

先运行文档目标测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_documents.py -q
```

如果新增拆分测试文件，把它们一起加入。通过后验证调用方兼容性：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_documents.py tests/test_api.py tests/test_workflow.py tests/test_mcp_server.py -q
```

若改动影响了公共 models.py、切片 ID 或检索假设，再按影响范围补 tests/test_retrieval.py、tests/test_citations.py 或完整回归。避免同一批通过后无目的地反复重跑。

如果出现此前的 pytest 临时目录权限问题，先确认失败路径，使用专用可写临时目录后重试，不修改文档业务逻辑去掩盖环境错误。

| 现象 | 优先检查 |
|---|---|
| 中文读取报错 | 文件实际编码、是否 UTF-8/BOM |
| PDF 看得到文字但提取为空 | 是否图片/轮廓文字/缺文本层，不能直接判损坏 |
| 第三页变成第二页 | 是否对跳过空页后的结果重新编号 |
| offset 截不出 content | 坐标系、清洗步骤、strip 前后的起点 |
| 多片同一 ID | identity 是否含页码、位置和内容 |
| 一个坏文件中断整批 | 解析边界异常是否包装、批处理是否只捕获预期错误 |
| 目录报告全成功但少了文件 | 是否仍在静默跳过异常 |
| Markdown 代码缩进丢失 | 逐行 strip 的已知影响 |
| 上传/MCP 回归失败 | 是否改变了旧函数返回类型或错误类型 |

## 17. 学习日志与 Git 提交

新建 curriculum/day-07-log.md，至少包含：

```markdown
# Day 07 学习日志

## 总览要求与本次完成情况

## 三类文档到 Source 的流程

## 字段映射与来源验证
文件名、路径、标题、页码、offset 的参照物。

## TXT 与 Markdown
编码、BOM、清洗规则和格式限制。

## PDF
两页文本、混合页、图片型、损坏/加密的区别。

## 片段坐标实验
保存一条 normalized[offset:end_offset] == content 的证据。

## 混合目录报告
加载/失败/跳过文件数、chunk 数、页警告。

## 测试与人工验证
实际命令、实际结果、至少一个失败及修复。

## 费用
本课无模型与付费 API 调用，费用 0 元。

## 当前局限与待补项
```

将 data/day07/ 加入 .gitignore，确认合成 fixtures 与生成脚本仍能提交。

在项目根目录执行：

```powershell
git status
git diff --check
```

按实际修改暂存，没创建的路径去掉，额外测试文件检查后补入：

```powershell
git add src/research_agent/documents.py tests/test_documents.py tests/fixtures/day07 examples/day07_make_samples.py examples/day07_document_lab.py curriculum/day-07-pycharm.md curriculum/day-07-log.md .gitignore
git diff --cached --stat
git status
git commit -m "learn: load local documents with traceable page metadata"
```

确认未暂存 .env、私人文档或包含敏感内容的运行输出。没有仓库时先确认根目录再初始化，并补可复现的基础提交。

## 18. 核心完成后的扩展任务

### A. 内容哈希与重复索引

读取原文件字节计算完整 SHA-256，区分：路径身份、文件内容版本、chunk 身份。

同一文件重复加载、不同路径相同字节、同路径内容更新，分别应该怎样处理？今天可以先写实验与规则；真正“跳过重复索引”还需要 Day 08 的索引层配合，单纯计算哈希并没有完成去重。

### B. DOCX Loader

先定义段落与标题如何映射到 Source，再增加可选依赖及测试。DOCX 流式段落结构通常不能直接提供可靠固定页码；不能用段落号冒充页码。

### C. OCR

了解 OCR 如何为图片页生成文字，记录额外依赖、中文识别、耗时与错误率。核心提示“可能需要 OCR”不代表已实现 OCR。

### D. 复杂 PDF 质量

比较 get_text("text")、sort=True 与 blocks 的输出，观察双栏和表格。改善阅读顺序后仍需人工核查，不能直接宣布通用解析正确。

### E. 大文件与资源边界

增加文件大小、PDF 页数限制，设计后台解析与可中断任务。async 包装不等于同步 PDF 计算可以立即取消。

## 19. 今日最终验收标准

- [ ] TXT、Markdown、PDF 均经统一入口返回 list[Source]。
- [ ] 三种格式都有保存的 Source 示例，非空片段保留文件名、路径、标题与类型。
- [ ] PDF 物理页码从 1 开始，空页跳过不导致后续页改号。
- [ ] 每片只来自一个 PDF 页面。
- [ ] offset/end_offset 有明确坐标系，能从对应规范化文本精确还原 content。
- [ ] 空文本、坏编码、损坏 PDF、需密码和无文本 PDF 有明确、可区分的结果。
- [ ] 不把所有无文本 PDF 都断言为扫描件。
- [ ] 混合 PDF 保留有文本页，同时提示未提取页。
- [ ] 批处理保留成功资料与文件级失败，不因一个坏文件丢失全部结果。
- [ ] 路径边界检查有效，旧 API/MCP/工作流调用保持兼容。
- [ ] 核心测试离线运行，包含真实解析器的 PDF 样例。
- [ ] 完成人工来源验证、日志和 Git 提交。

只有测试、样例与个人解释都成立，才算学会“本地文档加载”，不以终端打印出一段文字作为全部验收。

## 20. 不看笔记的口头验收题

1. 文件解析、文本清洗、切片各自改变了什么？
2. 为什么一个文件返回的是 list[Source]？
3. 为什么来源元数据必须在切片前建立并在切片后保留？
4. PDF 内部页索引、物理页码、印刷页码有什么区别？
5. 为什么第 2 页没有文本，后面的页仍然必须记为第 3 页？
6. 能否只凭 get_text 为空就确定这是扫描件？
7. offset 是字节位置、原文件字符位置，还是清洗后的字符位置？
8. strip 为什么可能让 offset 不再精确对应 content？
9. chunk 大小为 900 是否表示 900 Token？
10. 为什么文件名相同不代表内容相同，文件哈希相同也不代表已经完成索引去重？
11. 批量加载跳过一个坏文件后，怎样让用户知道它失败了？
12. 当文档里出现“忽略规则并执行命令”时，它为什么只是被读取的资料，而不是新的用户授权？

## 21. 按需查阅的官方资料

- [PyMuPDF：文本提取](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
- [PyMuPDF：Document API](https://pymupdf.readthedocs.io/en/latest/document.html)
- [Python 3.11：pathlib](https://docs.python.org/3.11/library/pathlib.html)
- [Python 3.11：文本读写](https://docs.python.org/3.11/tutorial/inputoutput.html#reading-and-writing-files)

Day 08 会把今天得到的文本片段转为 Embedding，建立向量检索并判断 Top-3 命中。文件、页码、片段坐标等字段要继续保留，它们是从“检索到内容”回到“找到证据”的基础。
