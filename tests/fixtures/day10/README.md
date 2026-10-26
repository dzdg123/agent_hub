# Day 10 固定案例规格（先定义输入与预期，再执行）

`cases.jsonl` 固定 R01～R15，共 15 个父案例；variants 是相同案例的子场景。
每条包含问题、来源键、检索/预算配置、期望状态、必要证据、禁止断言、Mock 输出或失败模式。
`@source_key` 是测试模板占位符：运行前绑定规范 Source ID，绝不从模型回复或资料标记创建来源。
来源 ID 由真实加载器生成时也使用同样的绑定，不依赖临时目录导致变化的内容 ID。

## 数据与网页来源

全部事实为合成实验数据，不声称对应真实研究。
sources.json 的 fixture_timestamp 是固定夹具时间，不是网页抓取时间；network_fetched_at 为 null。
网页使用 https://example.test/day10/result，正文为12%，搜索摘要元数据故意为99%。
禁止访问实时搜索或网站，审核基于保存的合成正文，不宣称刚刚重新验证网页。
PDF 根据 pages 数组在临时目录生成，第一页空白、第二页有文字；不保存机器相关的二进制路径。

## 两层执行

- fixed：直接构造规范 Source，注入固定模型脚本，隔离检验状态、校验、修复、审核和渲染。
- e2e：R01～R05 用当前文档加载器加载 TXT/Markdown/PDF，网页使用合成正文 Source；
  再用现有 KeywordIndex.search、来源过滤、build_context（通过 prepare_evidence_scope）、
  generate_answer、审核记录和渲染跑通。生成模型仍是 Mock，不是付费模型或检索质量评测。

固定预算按完整渲染块字符数计算，R10 明确保留主题资料、遗漏唯一支持来源；
变体覆盖预算一个块都装不下。R09 覆盖检索无候选与过滤范围为空。
R15 的 model_failed 对应课程中的 generation_failed，不能映射成 insufficient_evidence。
网络子场景用模拟 HTTP 执行客户端的真实有限重试代码，不发起真实请求。

## 审核与统计边界

review 是 AI 辅助编写的固定期望审核夹具，记录 reviewer、方法和理由；不是实际真人验收。
R13 故意写错而被拒绝，说明规则测试成功，不能记为真实 DeepSeek 的一次错误。
规则通过率和真实模型质量单独统计：本套规则测试真实模型调用数为0，真实模型错误率未测量。
必要证据/禁止断言用于逐项固定断言，不宣称实现通用语义判定算法。

预期成功的固定样例会提交带明确夹具身份的审核记录，验证正式渲染门控；
失败草稿只留诊断，不能生成正式报告。R13 即使程序校验通过也必须阻止正式渲染。

## 运行

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_day10_cases.py -q
.\.venv\Scripts\python.exe examples/day10_evaluate.py
```
