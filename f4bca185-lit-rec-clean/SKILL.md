---
name: lit-rec-clean
description: 文献抽取记录清洗与标准化：列名同义映射（F 系）、单位规范化（原值+换算值+公式与规则编号留痕，含 SI 前缀/复合与指数单位）、缺失与"未报告"区分、疑似重复识别、变更日志与可追溯导出。用于把论文抽取的脏记录清洗成可统计表且改动可回溯到输入行与规则编号的任务。
---

# lit-rec-clean：文献数据清洗与标准化

## 何时使用
输入为论文/附件抽取的批量记录（`/input/case.json` 记录列表、CSV，或含 records/data/rows/items 的 JSON），任务要求字段规范、单位换算、缺失/异常标注、去重并交付可复核结果。不裁决科学冲突——只识别并标注。

## 输入与输出
输入 `/input/case.json` 与 `/input/task.md`；输出写 `/app/output`：
- `cleaned_table.csv`：规范表，原值（value_raw/unit_raw）与换算值（value_std/unit_std）并存。
- `change_log.csv`：逐条变更：row_ref + source_ref + 字段 + 原值 + 新值 + rule_id + 公式。
- `anomaly_report.json`：missing / not_reported / unknown_units / unparsed_values / out_of_range / duplicates / possible_replicates / needs_review / unmapped_fields / encoding_notes。
- `cleaning_summary.json`：行数、状态与规则命中、列映射、来源清单。
- `result.json`：case_id/status/answer/sources/uncertainty/change_log 汇总。

## 运行步骤（Agent 严格照做）
1. 读 task.md 与 case.json，确认记录列表位置（嵌套键记下列名）与 output_contract 要求字段。
2. 跑引擎（先出诚实 result.json）：`python3 /skills/weekly-skill/scripts/clean_tabular.py --input /input/case.json --outdir /app/output --case /input/case.json`（必要时加 --list 键名）。
3. 读 cleaning_summary.json 与 anomaly_report.json，回答 task.md；答案须能回到 cleaned_table 行与 source_ref。
4. 把 output_contract 答案写 `/app/work/answers.json`，重跑步骤 2 并加 `--answers /app/work/answers.json --task-status success|partial` 更新 result.json。
5. 核对 result.json：case_id、status、answer、sources、uncertainty 齐全且诚实。

## 预算纪律
- 每案例 ≤12 次模型请求、全程 ≤600 秒（平台上限 64/900）；步骤 1–5 各 1–2 次请求，禁止无目的重跑；步骤 2 完成即有诚实 result.json，中断时 /app/output 仍可复核。

## 规则库（有编号、优先级、可增删；改 JSON 即生效）
- `resources/field_dictionary.json`（F 系）：列名同义→标准字段；同写法多命中 priority 高者胜；拆分字段值不同则拼接；未命中保留原名入 unmapped_fields。
- `resources/unit_rules.json`（U 系）：`std = raw*factor + offset`；prefixable 允许 SI 前缀（nm、kPa）；复合单位 `a/b`、`a b-N` 与指数单位 `cm2/cm²/cm-2`（→m2/m-2）按幂解析；ranges 越界检查。
- `resources/synonyms.json`（S 系）：物质/指标同义归一；只统一写法，修饰词差异留痕待确认，防错并。
- 换算不确定或规则缺失：原值保留、入 needs_review，绝不编造。

## 异常处理（诚实保留与标注）
- 单位不明：status=unknown_unit，原值保留，入 needs_review。
- 缺失 vs 未报告：空串/占位符（-、N/A、null）→ missing；NR/未报告 → not_reported；均保持数值空缺。
- 疑似重复：同物质+指标+条件且换算后等值 → duplicates（待确认合并）；同键取值不同 → possible_replicates（全部保留）。
- 编码错乱：自动修复常见 mojibake（µ/°C/±）记 encoding_notes；空表/不可读：status=partial/failed 写明原因与人工接管位置。

## 可追溯性与确定性
value_std 沿 change_log 的 row_ref→输入行→source_ref、rule_id→规则公式回溯；同义归一亦留痕；重复运行逐字节一致（status_counts 已排序）。

## 最小调用示例（自拟材料，标注示例）
见 `examples/example_input.csv` 与 `examples/example_output.md`（示意，非正式案例结果），覆盖列名映射、°F→°C、复合/指数单位、NR、越界、未知单位与重复识别。

## 自查清单
result.json 含 case_id + output_contract 全部字段 + 诚实 status/sources/uncertainty/change_log；change_log 每行有 row_ref 与 rule_id；needs_review 非空时 status 不得为 success；六方面（字段规范、单位转换、同义归一、缺失与异常、重复记录、来源与变更）齐备且原始值未被改写。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/read_tool.py support_check answers.json --text source.txt` 把每条证据引文在原文里做逐字匹配，不在原文的（误报）直接揪出；支持度分档统计。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：证据逐字回链、支持度分档。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/support_rubric.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/support_rubric.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
