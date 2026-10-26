# 阶段六：Markdown 渲染与来源定位

实现位于 `src/research_agent/rag_render.py`，每次从结构化数据重新生成。
旧 `citations.append_references()` 和旧 workflow 路径保持原接口，不在新渲染器中调用。

## 两个渲染入口

```python
from pathlib import Path
from research_agent.rag_render import render_answer_preview, render_answer_markdown

# 结构/来源通过，support_review=pending 时，只能生成明确标记的预览。
preview = render_answer_preview(result, scope.visible_sources, base_dir=Path(project_root))

# 完成阶段五的逐项内容审核后，正式渲染会再次调用 can_publish_answer 检查。
markdown = render_answer_markdown(reviewed, scope.visible_sources, base_dir=Path(project_root))
```

`project_root` 为调用方明确指定的项目根目录。相对本地路径据此解析；未指定 base_dir 时，
相对本地路径只显示文本。绝对路径无需依赖当前工作目录。

预览只接受 pending；审核失败的回复只保留诊断，不能伪装成正常报告。
已通过审核的报告使用正式入口。两个入口都重验 Schema、业务规则、规范来源和版本指纹，
并拒绝被改写的路径、页码、摘录位置。渲染不修改原对象，也不自动调用模型。

## 引用与参考资料

- 按原始 claims/evidence 首次使用顺序分配 ref-1、ref-2，不使用 source_id 作为 HTML 属性。
- 正文显示 source_id 并链接到相应 ref-N；标签经过转义，ID 原值保存在结构化数据中。
- 每条说法中同一来源的多个摘录只生成一次来源链接。
- 参考资料仅包含实际引用的来源；按 source_id 去重，不按 PDF 文件名合并。
- 地址、标题、物理页和位置来自规范 Source/重新计算的精确摘录位置，不接受模型生成的地址。
- 同 ID 来源存在重复或冲突时，来源层失败，不能渲染。
- 事实、明确标记的推断、局限分别组织；partial 和 insufficient_evidence 明示资料缺口。
- 位置标明为左闭右开字符区间，不能解读为原文件字节或 PDF 版面坐标。
- 不带入上次 Markdown，不追加旧参考资料，相同输入会生成相同输出。

所有自由文字按普通文本转义，包括标题、来源标签、说法和局限。
结构层拒绝 claims.text/limitations 中的配对方括号引用、〔引用〕、【引用】、HTML 和网址；
引用只能由 evidence 字段生成。当前短答规则也会拒绝 `数组[0]` 这类配对方括号写法，
可改用文字表达；后续需要支持代码时，应单独设计明确的文本语法。
quote 忠实保留原文，即使含方括号或 HTML 也不改写，且不会作为可执行 HTML 渲染。

网页仅为有效的 http/https 地址生成链接；其他协议和异常 URL 只显示转义文本。
URL 的空格、括号、引号等按 URI 编码，不能逃出 Markdown 链接边界。
本地 PDF 可生成 #page=N 链接，同时保留文字物理页码；查看器不一定支持跳页。
不将 file:、javascript:、UNC 等协议/地址自动转成可点击的本地链接。

## 显式核对文件存在性与 PDF 页数

纯渲染不会访问网页或打开本地文件。需要实际检查时调用：

```python
from research_agent.rag_render import audit_reference_locations

issues = audit_reference_locations(result, scope.visible_sources, base_dir=Path(project_root))
for issue in issues:
    print(issue.code, issue.path, issue.message)
```

此函数只检查实际被引用的来源：本地文件是否存在、PDF 是否可读取、物理页码是否在实际页数内，
以及网页 URL 是否符合链接规则。它不请求网页，不执行文件，不重新认证摘录与当前文件内容。
需要文件核验的发布流程应在发现 issues 时阻止发布；不能把纯渲染成功当作文件检查通过。

## 实验脚本

直接看离线草稿预览，不消耗 API：

```powershell
.\.venv\Scripts\python.exe examples/day10_answer_lab.py --mode mock --case success --format markdown
```

真实调用并输出草稿预览，会产生 API 用量：

```powershell
.\.venv\Scripts\python.exe examples/day10_answer_lab.py --format markdown
```

Markdown 写到 stdout，用量摘要写到 stderr。默认 JSON 格式仍保留完整回复和诊断，
并增加 markdown_preview 字段。没有有效草稿时不渲染原始错误回答。

测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rag_render.py tests/test_rag_validation.py tests/test_day10_answer_lab.py -q
```
