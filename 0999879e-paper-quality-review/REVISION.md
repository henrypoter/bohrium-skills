# 论文质量审查修订说明（v2 → v3）

日期：2026-11-25；工具版本：`3.0.0`；结果契约：`2.0.0`。本版只改本题提交目录，没有修改共享核心、提交或 push。

## 1. 实际效果（40）：从“有字段”升级为可执行验收闭环

### 完成度与正确性

- v2 的 `verify --text` 去掉空白后做子串匹配，可能把并非逐字的引文判为通过；也没有校验位置是否真实。本版 `index` 固定页/行/段/句/字符偏移，`verify` 对每个主证据和辅助证据同时检查：**原始逐字 quote、end-exclusive 偏移、页/行/段/句、源 SHA-256、quote SHA-256**。不传来原文直接失败，不再静默跳过。
- 新增 `citations`：实际解析数字方括号引用、区间和参考文献，输出本文论断句—题录 pair 及悬空引文的准确定位和补条/改号动作。`support` 只能先为 `not_checked`，防止把“有参考文献”误当“引用支持”。语义支持必须读被引来源，双 span 才能 confirmed。
- `schema` 强制 `type=fact_error/insufficient_evidence/normative_issue/suggestion`、严重度、confirmed/needs_review、依据和具体 fix；`fix.target=注意`、`instruction=建议检查` 会失败。缺失声明必须有全范围 `absence_evidence`，不能用空引文或伪造原句。

### 完整性与可核验性

- v2 用“某类有没有 issue”推断覆盖，会把零问题误写为未查。本版 `coverage` 要求 fact/citation/design/statistics/argument/compliance 六类逐一登记 checked/partial/not_applicable/not_checked；checked 有 search_scope，其余有 reason。
- `result.json` 强制 `result_schema_version=2.0.0`、`tool_version=3.0.0`、case_id、原始文件与抽取文本双 SHA-256、解析器、sources、unchecked、uncertainty、change_log。
- `bench/fixtures/good_result.json` 已从旧版不兼容结构重写为真实可回验 synthetic 示例；实际通过 `verify + coverage + schema`。

## 2. 使用增益（25）：对照可执行且禁止编分

- 新增 `compare`：两臂必须同 case_id、同稿件文本哈希；`decisions.json` 必填共享 `permissions/allowed_sources/budget`，逐 issue 独立裁决 supported/unsupported/unresolved。
- 输出 decided precision、误报率、unresolved 数及两臂差值，并读取真实 `elapsed_seconds/manual_review_seconds/rounds` 计算效率差值。裁决 ID 不全、跨稿件、缺少共享权限/资料/预算说明均失败。
- 平台未给真实基线时，`gain.status=not_measured` 且必须写原因。bench 对照仅验证算法，不冒充三个官方案例的增益。

## 3. 创新增益（15）：相对基础 Agent 的稳定新增边界

1. **精确证据防漂移：** 基础 Agent 可写 location/quote，但通常没有机器保证；本 Skill 用坐标 + 哈希 + 原文逐字回验拒绝错位和 paraphrase。
2. **引用—论断对照：** 自动完成数字引文的结构解析和配对，强制把“题录命中”与“语义支持”分开。边界：作者—年份引用、题录真实性、语义支持和外部事实仍需实际来源/人工裁决。
3. **覆盖与增益可证伪：** 六类状态不由问题数推断；对照不因字段存在就产生增益分。

## 4. 可靠体验（10）：点名异常均有信号与恢复动作

`SKILL.md` 异常表逐项覆盖：解析失败/缺页、图表不可读、参考文献缺失、原文歧义、稿件超长、数据与结论冲突，另加重复运行不一致。每项列识别信号、重试/降级/unchecked/人工动作；抽样不冒充全文，无全文不确认引用错配，无法判哪个数值正确时不擅改。

## 5. 生态贡献（10）：资源与实跑证据

- 更新：`SKILL.md`、`docs/README.md`、`templates/checklist.md`、synthetic 稿件和 result 示例。
- 可复用工具：`scripts/review_tool.py`，无第三方依赖。
- 自测：`bench/bench_run.py`，每个命令包含正向零误杀和变异必命中，另测多来源证据、空泛 fix、缺失检索、跨输入比较、共享资料缺失等。
- **最终 bench：23/23 PASS。** 运行命令：`python3 bench/bench_run.py`。

## 距离榜首/满分仍需真实证据的部分

- 尚未在组织方隐藏的三案运行，不能据此声称官方命中率、效率、增益或排名；真实三案的基础 Agent 对照与独立裁决是最大缺口。
- 数字引文之外的格式、语义支持、PDF 复杂版面/扫描 OCR、图表像素内容和学科特定方法判断仍依赖人工或实际环境能力。
- compare 目前报告 decided precision 和效率；若没有独立金标准，不能把漏报率/召回率包装成已知指标。
- `GITHUB_URL.txt` 保留原链接，本次未进行未登录可用性验证；公开链接附加分仍需实际核验。
