# 数据格式、安装与维护

## 一、安装与依赖

- 仅 Python 3 标准库（re/sys/json/pathlib），Python 3.8+；无需 pip 安装、无网络依赖。
- 拷贝 `scripts/fact_tools.py` 与 `templates/` 即可使用；自测：`python3 tests/run_tests.py`（exit 0 为通过）。
- 输入材料为 UTF-8 文本；PDF 先用环境预装工具转文本再处理。

## 二、fact_ledger.json（extract 产物）

| 字段 | 类型 | 含义 |
|-|-|-|
| sources | [str] | 实际读取的材料路径 |
| numbers | {规范键: [例句…]} | 数值+单位（规范化：去千分位、μ→u、去尾零；中文数字转阿拉伯；**不含图表/引用编号**） |
| sample_sizes | [str] | n=N 样本量 |
| fig_refs / citations | [str] | 图表编号 / 引用编号（专门字段核对） |
| abbreviations / abbr_definitions | [str] / {缩写: 全称} | 大写缩写及其源文展开 |
| strong_claim_words | [str] | 源文自身已用的强论断词（成稿同级保留不报越级） |
| caveats | {组名: [源句…]} | 限定语四组：待验证 / 初步·小样本 / 仅限·范围 / 未同行评议 |
| causal_words / correl_words / advice_words | [str] | 非否定、非限定句中实际断言的因果/相关/建议词 |
| asserted_subject_tier_idx | [int] | 已断言研究对象层级（0 体外<1 动物<2 人体<3 应用）；限定/否定句不计入（保守） |

## 三、check_report.json（check 产物，9 违规类 + 2 提示类 + 体裁）

| 字段 | 性质 | 处置 |
|-|-|-|
| added_numbers_not_in_source | 违规 | 删除或改写为有出处表述后重核 |
| source_numbers_missing_in_draft | 违规 | 补回；或确认属体裁性删除并记 change_log |
| strong_word_escalation | 违规 | 降级为源文同级表述 |
| caveats_missing | 违规 | 补等价限定语（对应论断整体删除则不报） |
| advice_escalation / causal_escalation / extrapolation_escalation | 违规 | 删建议 / 降为相关 / 降为「有待验证」 |
| unexplained_abbreviations | 违规 | 首现展开或删除 |
| fig_refs_missing / citations_missing | 提示 | 补回；或体裁性删除记 change_log 并保留来源说明 |
| genre_compliance | 结构 | missing_required 列缺项；未知体裁 pass=None 跳过 |

result.json 全字段契约见 templates/result_schema.md；`fact_source_map` 每条 `{fact, draft_expression, source_locator, action, reason}`，`change_log` 每条 `{location, action, reason}`，`term_glossary` 每条 `{term, expansion_or_plain, locked_form}`。

## 四、体裁模板格式与样例

机器可读部分：`GENRE_SECTIONS = {体裁: {必备段: [触发词…]}}`（fact_tools.py 顶部），任一触发词出现即视为该段具备，另强制 `#` 标题。人工可读骨架与取舍规则见 templates/genres.md §二。

填充样例（科普文章）见 examples/example_case.md 与 tests/fixtures/clean_draft.md。技术转移报告迷你样例（骨架填充示意，非真实数据）：

```markdown
# XX 催化剂技术转移报告
## 成果概述 …（一句话成果+来源）
## 技术要点 …（方法要点，保留统计口径）
## 性能指标 …（数值/单位/对比基准，标注来源段落）
## 成熟度 …（无 TRL 信息则【材料缺口】）
## 应用场景 …（区分已支持/推断）
## 风险与待确认 …（限定语、open_questions）
```

## 五、维护与版本

- 版本：v3（2026-11-16）。变更记录：SOLUTION.md v1→v2→v3 三节。
- 扩词表：改 fact_tools.py 顶部常量（STRONG/CAVEATS/CAUSAL/CORREL/ADVICE/SUBJECT_TIERS），改完必须跑 `python3 tests/run_tests.py` 保证正向零误杀。
- 扩体裁：在 GENRE_SECTIONS 加必备段触发词 + 在 genres.md §二加骨架 + 在 examples 或 fixtures 补一个样例。
- 质量门禁：tests/run_tests.py 22 项全过（exit 0）才允许提交；夹具为虚构材料，非正式案例。
