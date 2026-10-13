# Day 07 学习日志：本地文档加载、来源追溯与 PDF 页码

日期：2026-10-13

## 总览要求与本次完成情况

Day 07 的目标是把磁盘上的 TXT、Markdown 和 PDF 转换成统一的 `Source`，并且让每个片段都能追溯到原文件、PDF 物理页和规范化文本中的字符位置。

本次完成了以下工作：

- 明确 `load_document(path, root) -> list[Source]` 的统一文档契约。
- 支持 UTF-8、带 BOM 的 UTF-8、TXT、`.md`、`.markdown` 和文本型 PDF。
- 区分空文本、坏编码、损坏 PDF、加密 PDF 和无文字层 PDF。
- PDF 按物理页解析和切片，空白页不会导致后续页码重新编号。
- 提取 `normalize_document_text()`，明确 `offset/end_offset` 的坐标系。
- 修复切片后 `.strip()` 可能造成的 offset 偏移。
- 为每个 Source 保存独立 metadata，避免修改一个片段污染其他片段。
- 增加路径边界检查和详细批处理报告。
- 保持旧的 `load_all_documents()` 返回 `list[Source]`，避免破坏已有调用者。
- 将文档测试按 T01～S01 的行为矩阵整理，最终 38 项测试全部通过。

本课没有调用模型、Embedding、向量数据库或付费 API。重点是把后续检索使用的输入资料准备正确。

## 三类文档到 Source 的流程

```text
允许根目录 root + 候选路径 path
  ↓
safe_document_path()
  ├─ resolve root 和 path
  └─ relative_to(root) 验证路径没有逃出允许目录
  ↓
load_document()
  ├─ 检查不存在、目录输入和不支持的后缀
  ├─ 建立文件级 metadata
  │    ├─ content_kind
  │    ├─ file_name
  │    ├─ relative_path
  │    └─ file_type
  │
  ├─ TXT/Markdown
  │    ├─ 使用 utf-8-sig 读取
  │    ├─ 区分 encoding_error 和 empty_document
  │    └─ 交给 _chunk_sources()
  │
  └─ PDF
       └─ _load_pdf()
            ├─ 检查损坏与密码
            ├─ 按物理页提取文字
            ├─ 记录无文字页
            └─ 每一页分别交给 _chunk_sources()
                 ↓
        normalize_document_text()
                 ↓
        按字符数量和边界切片
                 ↓
        list[Source]
```

不能混淆以下数量：

- 文件数：目录中尝试加载了多少个文件；
- 页面数：一个 PDF 有多少个物理页；
- Source 数：经过逐页处理和切片后产生多少个片段。

一个文件可以产生多个页面，一个页面也可以产生多个 Source。

## 主要函数和职责

| 函数或类型 | 职责 |
|---|---|
| `DocumentLoadError` | 统一预期文档错误，并用可选 `code` 分类 |
| `safe_document_path()` | 解析路径并阻止候选文件逃出允许根目录 |
| `load_document()` | 单文件统一入口，分派文本和 PDF 加载器 |
| `_load_pdf()` | 检查 PDF、逐页提取文字并保留物理页码 |
| `normalize_document_text()` | 删除空行、清理每行首尾空白并用换行重新连接 |
| `_chunk_sources()` | 验证参数、切片、修正 offset 并创建 Source |
| `load_all_documents_detailed()` | 批量加载，并返回成功来源、错误、警告和统计 |
| `load_all_documents()` | 兼容旧调用者，只返回成功的 `list[Source]` |
| `DocumentBatchResult` | 保存批处理 sources、errors、warnings 和文件统计 |

## 字段映射与来源验证

每个本地文档片段使用统一的 `Source`，关键字段含义如下：

| 字段 | 含义 |
|---|---|
| `source_id` | 当前片段身份，由路径、页码、起点和内容共同参与生成 |
| `title` | TXT/Markdown 使用文件名，PDF 增加“第 N 页” |
| `content` | 当前非空片段的文本 |
| `file_path` | 解析后的绝对路径 |
| `page` | PDF 从 1 开始的物理页码；文本文件为 `None` |
| `metadata.content_kind` | 固定为 `local_document` |
| `metadata.file_name` | 包含扩展名的文件名 |
| `metadata.relative_path` | 相对于允许根目录的路径 |
| `metadata.file_type` | `txt`、`markdown` 或 `pdf` |
| `metadata.chunk_index` | 当前文本单元内从 0 开始的片段序号；PDF 每页重置 |
| `metadata.offset` | 片段在规范化文本中的字符起点 |
| `metadata.end_offset` | 片段结束位置，不包含该位置 |
| `metadata.offset_basis` | `normalized_document_text` 或 `normalized_page_text` |

来源验证思路：

1. 用 `file_path` 回到原始文件。
2. PDF 用 `page` 回到对应物理页。
3. 用该文档或该页的规范化文本以及 `offset:end_offset` 还原 `content`。

`source_id` 当前代表片段，不代表跨电脑、跨路径和跨切片规则永远不变的文档身份。移动文件或改变切片参数，都可能改变 ID。

## TXT 与 Markdown

### 编码规则

文本文件使用：

```python
path.read_text(encoding="utf-8-sig")
```

这样普通 UTF-8 和带 BOM 的 UTF-8 都可以读取，BOM 不会进入正文。

没有使用 `errors="ignore"` 读取文件，因为它会静默删除无法解码的字节，让坏编码看起来像成功文件。非 UTF-8 文件会得到：

```text
code = encoding_error
```

### 空文本规则

以下两种情况都属于 `empty_document`：

- 0 字节文件；
- 只有空格、制表符或换行的文件。

空文本不会创建空 Source。

### Markdown 清洗限制

当前规范化规则是：

```python
"\n".join(
    line.strip()
    for line in text.splitlines()
    if line.strip()
)
```

标题、列表标记和代码内容会进入 Source，但该规则会：

- 删除空行；
- 删除每行首尾空白；
- 改变嵌套列表和代码块缩进；
- 不能声称完整保留 Markdown 原始排版。

今天的目标是保证文本可检索。若后续需要忠实保留代码排版，应为 Markdown 单独设计更保守的解析规则。

## PDF

### 物理页码

`_load_pdf()` 使用：

```python
for page_number, page in enumerate(document, start=1):
```

因此 page 表示 PDF 文件中的物理页，从 1 开始。它不是页面上印刷的页码，也不是目录中的逻辑页标签。

每页分别调用 `_chunk_sources()`，所以一个 Source 不会跨 PDF 页面。

### 混合页

三页实验中：

```text
第 1 页：有文字
第 2 页：没有可提取文字
第 3 页：有文字
```

结果 Source 的页码是 `{1, 3}`。第 2 页执行 `continue` 不会让第 3 页变成 page=2。

无文字页保存为：

```text
empty_pages = [2]
warning_code = no_text_on_page
```

混合 PDF 仍属于成功文件，因为它产生了可用 Source；同时必须报告部分页面未提取到文字。

### 图片型、空白、损坏和加密 PDF

| 场景 | 当前结果 |
|---|---|
| 正常文本 PDF | 返回逐页 Source |
| 混合 PDF | 保留有文字页并报告无文字页 |
| 图片型 PDF | `no_extractable_text` |
| 全空白 PDF | `no_extractable_text` |
| 损坏或 0 字节 PDF | `parse_error` |
| 需要密码的 PDF | `password_required` |

图片型 PDF 实验不是简单创建空白页，而是：

```text
文本 PDF 页面
→ get_pixmap()
→ 新建 PDF 页面
→ insert_image(..., pixmap=...)
→ 只保存图片
```

生成的页面肉眼可以看到文字，但 `get_text("text")` 返回空字符串，因为 PDF 内没有文字层。

当前没有启用 OCR。`no_extractable_text` 只能说明解析器没有获得文字，不能断言文件一定是扫描件。空白页、纯图片、特殊字体或其他结构都可能造成无文本结果。

代码使用 `import pymupdf`，没有继续使用已提示弃用的 `fitz` 导入名。

## 错误边界与错误代码

预期文件错误统一转换为 `DocumentLoadError`，并使用异常链保留原始原因：

```python
raise DocumentLoadError(
    "文档解析失败：请检查文件是否损坏",
    code="parse_error",
) from exc
```

本次使用的主要 code：

| code | 含义 |
|---|---|
| `outside_root` | 候选路径解析后位于允许目录之外 |
| `not_found` | 文件或详细批处理根目录不存在 |
| `not_a_file` | 单文件入口收到目录路径 |
| `not_a_directory` | 批处理根路径不是目录 |
| `unsupported_type` | 后缀不受支持 |
| `encoding_error` | 文本不是支持的 UTF-8 编码 |
| `empty_document` | 文本为空或只有空白 |
| `parse_error` | PDF 损坏或读取/解析失败 |
| `password_required` | PDF 需要密码 |
| `no_extractable_text` | 整份 PDF 没有产生可提取文本 |

异常捕获范围只围绕实际读取和 PDF 解析，不使用覆盖整个加载、规范化和切片过程的 `except Exception`。这样切片算法中的 `ValueError` 或开发错误不会被伪装成“文件损坏”。

PDF 通过 `with pymupdf.open(...)` 管理，即使中途失败也会关闭资源。

## 片段坐标实验

offset 的坐标系是 Python 规范化字符串的字符位置：

```text
TXT/Markdown：规范化后的整篇文本
PDF：对应物理页规范化后的单页文本
```

它不是：

- UTF-8 字节偏移；
- 编辑器里的原始行列；
- PDF 页面坐标；
- 整份 PDF 拼接后的全局位置。

中文在 Python 字符串索引中按字符计数：

```python
len("中文") == 2
len("中文".encode("utf-8")) == 6
```

### 最小英文实验

输入：

```text
ABCDEFGHIJKLMNO
```

参数：

```text
chunk_size = 6
overlap = 2
```

结果：

| offset:end_offset | content |
|---|---|
| `0:6` | `ABCDEF` |
| `4:10` | `EFGHIJ` |
| `8:14` | `IJKLMN` |
| `12:15` | `MNO` |

核心证据：

```python
assert normalized[
    source.metadata["offset"]:
    source.metadata["end_offset"]
] == source.content
```

原实现先执行 `normalized[start:end].strip()`，却仍保存原始 `start`。如果片段开头是空格或换行，offset 会与实际 content 错位。本次通过计算 `left_trim` 得到 `content_start`，再用内容长度得到 `content_end`，解决了这个问题。

下一片仍根据原始 `end/overlap` 推进，避免展示文本裁剪影响循环前进。

参数约束为：

- `chunk_size` 必须是正整数；
- `overlap` 必须是非负整数；
- `overlap < chunk_size`；
- 非法参数在进入 while 前拒绝；
- 下一次 start 至少比当前 start 大 1，避免无限循环。

默认值仍为 900/120。它们表示字符数量，不是模型 Token 数，也不是已经证明适合所有文档的最佳参数。

## 路径边界与 metadata 独立性

调用约定：

```python
root = Path("data/day07/input").resolve()
path = root / "two_pages.pdf"
sources = load_document(path, root)
```

`Path("two_pages.pdf")` 会相对于进程工作目录解析，不会自动拼接到 root。实验中曾因为 PyCharm Working directory 与预期不同而出现 `FileNotFoundError` 和“文档目录不存在”。最终演示脚本改为根据 `__file__` 计算项目根目录：

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
root = PROJECT_ROOT / "data" / "day07" / "input"
```

这样从 PyCharm 或其他工作目录运行时都能定位到正确目录。

路径测试证明：

- root 内正常文件可以加载；
- `../` 逃出 root 会被拒绝；
- `docs-other` 不能利用与 `docs` 相同的字符串前缀通过检查；
- 不存在、目录输入和不支持类型得到不同 code。

每个片段使用 `deepcopy(base_metadata)` 得到独立 metadata。测试中修改第一片的嵌套 `warnings` 列表后，第二片保持不变。

## 混合目录报告

详细入口：

```python
load_all_documents_detailed(root) -> DocumentBatchResult
```

返回内容包括：

- `sources`：所有成功片段；
- `errors`：文件级失败记录；
- `warnings`：部分页面提醒；
- `loaded_files`：成功产生 Source 的文件数；
- `failed_files`：失败的受支持文件数；
- `skipped_files`：未尝试的不支持类型文件数。

失败记录只保存相对路径、错误 code 和简短消息，不把文档正文写入日志。

固定 9 文件场景通过 pytest 使用 `tmp_path` 生成，结果为：

```text
loaded_files = 4
failed_files = 4
skipped_files = 1
```

其中 `mixed.pdf` 同时产生成功 Source 和第 2 页警告，不重复计入失败文件。

当前 `data/day07/input` 实际演示目录只包含本地生成的部分样例，因此演示脚本的实际输出是：

```text
loaded_files = 2
failed_files = 1
skipped_files = 1
sources = 4

error:
  image_only.pdf → no_extractable_text

warning:
  mixed_pages.pdf page=2 → no_text_on_page
```

这里的 `skipped_files=1` 来自目录中的 `.py` 生成脚本。该结果与固定 9 文件测试不是同一输入集合，所以统计不同是正常的。

旧入口继续兼容：

```python
load_all_documents(root) -> list[Source]
```

旧入口仍会创建缺失 root，并只返回成功来源。详细入口不会默默创建拼错的目录，而是返回 `not_found`。

## 测试与验证

文档测试按以下顺序整理：

```text
T01～T05：TXT、BOM、Markdown、空文本、坏编码
P01～P06：正常、多页、混合、图片、空白、损坏、加密 PDF
C01～C03：offset、参数边界、metadata 独立
B01：混合目录批处理
S01：根目录边界
```

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_documents.py -q
```

实际结果：

```text
38 passed in 0.40s
```

测试资料都由 `tmp_path` 和真实 PyMuPDF 临时生成，不读取用户私人目录，不依赖互联网，也不把临时路径写死为某个用户名。

### 本次遇到的问题和修复

1. **坏编码没有被发现**
   - 原因：读取时使用 `errors="ignore"` 会静默丢弃非法字节。
   - 修复：移除 ignore，捕获 `UnicodeDecodeError` 并转换为 `encoding_error`。

2. **相对路径找不到 PDF**
   - 原因：相对路径按 PyCharm Working directory 解析，不是按 root 或脚本目录自动解析。
   - 修复：样例脚本使用 `Path(__file__).resolve()` 构造绝对路径。

3. **图片型 PDF 与空白 PDF 概念混淆**
   - 原因：只有空白页不能证明“肉眼有文字但没有文字层”。
   - 修复：把文本页渲染为 Pixmap，再作为图片插入新 PDF，并验证 `get_text()` 为空。

4. **错误消息与错误 code 混淆**
   - 原因：测试曾用 `match="encoding_error"` 检查消息，但 code 已经是单独属性。
   - 修复：使用 `exc_info.value.code == "encoding_error"`。

5. **测试入口 NameError**
   - 原因：调用 `load_all_documents_detailed()` 时忘记导入。
   - 修复：统一整理测试文件顶部导入。

6. **测试文件语法错误**
   - 原因：断言末尾误输入中文顿号。
   - 修复：删除非法字符并重跑整份测试。

## 掌握的知识

完成 Day 07 后，我能够解释和应用以下知识：

1. **统一数据契约**：不同文件格式最终都进入 `Source`，下游不必针对每种文件重新设计接口。
2. **来源追溯**：文件路径、相对路径、物理页码、offset 和 source_id 分别解决不同层次的身份问题。
3. **字符与字节的区别**：Python 字符串 offset 不等于 UTF-8 字节位置。
4. **PDF 页码语义**：解析循环中的物理页码不能因空白页被压缩或重新编号。
5. **有图不等于有文字层**：PDF 能打开、肉眼可见文字和解析器能提取文字是三件不同的事。
6. **部分成功**：混合 PDF 和混合目录不能因为局部失败就丢弃全部成功资料，也不能静默隐藏失败。
7. **异常边界**：只转换预期文件错误，保留异常链，不用宽泛捕获掩盖代码缺陷。
8. **路径安全**：路径边界必须基于解析后的 Path 关系，而不是字符串前缀。
9. **可验证切片**：正确的片段不只要“看起来合理”，还要能通过 offset 从规范化文本精确还原。
10. **可重复测试**：用 `tmp_path`、合成小文件和真实解析器建立不依赖网络与私人数据的固定验证。

## 人工质量验证说明

自动测试已经证明结构和契约正确，但自动测试不能完全替代视觉检查。仍应在 PyCharm 或 PDF 阅读器中人工确认：

1. `two_pages.pdf` 的文字可以选择和复制，内容与 `get_text()` 基本一致；
2. `image_only.pdf` 肉眼能看到文字，但无法通过解析器提取文字层；
3. 任意 PDF Source 的 `page` 能回到正确物理页；
4. Markdown 经过当前清洗后，缩进和空行损失是否仍在可接受范围。

必须分清四件事：

```text
文件能打开
≠ 有可提取文本
≠ 抽取质量合格
≠ 有准确来源
```

## 费用

本课没有模型调用和付费 API 调用，费用为 0 元。

## 当前局限与待补项

- 没有 OCR，图片型 PDF 只能报告无可提取文本。
- Markdown 规范化会破坏缩进和空行，尤其可能影响代码块展示。
- PyMuPDF 默认文本顺序不保证适合双栏、表格、页眉页脚等复杂版面。
- 当前 chunk 大小按字符计数，不是 Token 数，也没有经过检索效果评估。
- `source_id` 是片段身份，不是跨设备稳定的文档 ID。
- 尚未实现内容哈希去重、DOCX、文件大小限制、PDF 页数限制和后台可取消解析。
- `load_all_documents()` 为兼容旧调用仍只返回成功来源；需要诊断时必须显式使用详细入口。
- 还需要完成上述人工 PDF/Markdown 质量检查，并只记录脱敏片段。

Day 08 将在这些可追溯、可测试的 Source 之上学习向量化和索引。今天建立的页码、offset、错误和 metadata 契约，是后续检索结果能够正确引用原始资料的基础。
