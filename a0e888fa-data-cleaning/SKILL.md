---
name: data-cleaning
description: 科研数据清洗与处理。用于含缺失、异常、近似重复、编码/单位故障的数据表、跨表连接和质量报告；按数据字典生成字段规则，保留原值与行号，可逆转换，并机检报告=结果=清洗表。纯标准库，支持失败降级与逐字段复核。
---

# 科研数据清洗与处理（v3.0.0）

**判对总闸：每个字段有“规则 + 理由 + 字典定位”，每处变更有“原值 + 行号 + 新值”，每个汇总有“快照 + 代码/公式 + 哈希”，最终报告数字必须等于结果摘要和清洗表实算值。** 不适用：把聚合转录当原始实验、因果/人口统计推断、专家无法确认的源值填补、数据库运维或论文写作。

## 1. 输入、输出与立即降级

读取 `/input/case.json`、`/input/task.md`、实际材料、数据字典、QC 规则和 workorder；先沿用原 `output_contract` 和 `case_id`，不得用本说明示例替代正式案例。平台材料若为发表论文聚合表的故障注入版本，只恢复约定存储/编码问题，**不补造个体观测，不填补无效/缺失源值**；不假设存在 `quality-gold.md`。

输出到 `/app/output`：`result.json`、`cleaned_table.csv`、字段规则、行级变更表、`quality_report.json`、转换审计、复算代码/日志；图表必须有对应记录表。开始即写带 `status:"partial"` 和 `unchecked` 的诚实结果，之后增量完善。`issues`=完成但有明示问题，`partial`=材料/权限不完整，`failed`=无法交付主结果。

工具均为 Python 3 标准库：`data_tool.py`（画像/聚合复算/旧契约）+ `cleaning_tool.py` v3.0.0（新四道机检闸）。从 Skill 根目录调用；安装后可用绝对路径 `/skills/weekly-skill/scripts/...`。

## 2. 可复跑流程

### 2.1 血缘、画像与字段策略（先做，未过闸不计算）

```bash
python3 scripts/data_tool.py profile data.csv
python3 scripts/cleaning_tool.py plan dictionary.json --csv data.csv > field_plan.json
```

`dictionary.json` 至少包含 `dictionary_version` 与逐字段 `semantic/role/unit/missing_tokens`；测量字段可加 `target_unit/physical_range`，分类字段给 `codes`，标识字段声明真实主键。示例（**接口示意，不是正式答案**）：

```json
{"dictionary_version":"dict-v1","fields":{
 "sample_id":{"role":"identifier","semantic":"样品编号","missing_tokens":[""]},
 "concentration":{"role":"measurement","semantic":"浓度","unit":"mg/L","target_unit":"μg/L","physical_range":[0,10000],"missing_tokens":["","-999","<LOD"]},
 "sex":{"role":"categorical","semantic":"性别编码","codes":{"1":"男","2":"女","9":"未知"},"missing_tokens":["","9"]}}}
```

`plan` 对每字段输出 `source`（如 `dictionary.fields.concentration.unit`）、缺失行号、缺失/异常/数值使用策略和待确认问题。默认“缺失只标记、不按均值补；IQR 只提示、不自动删；编码不当连续值；单位不明不转换”。空表、全列缺失、未知字段语义和单位不明均为 blocker。`profile` 的 `missing/duplicate_rows/outliers_iqr/scale_warning/dirty_numeric_count` 写进质量记录，不要把算术缺失、未检测、低于检出限和真值 0 合并。

### 2.2 异常和重复：按真实主键与物理约束裁决

- 物理上下限优先于分布提示；IQR 高值保留原值并注明“真实高值/录入错误待确认”的证据，未经 workorder 不剔除或盖帽。
- 完全重复只是线索。按样品/受试者/时间戳及版本确定键，保留规则写入 `row_changes`；1:N 连接先聚合子表，不能令样本量膨胀。
- 跨表对齐先跑以下命令。归一化只用于匹配，原键原样保留；空键、规范化后重复、同键公共字段冲突均带 CSV 行号阻断，未匹配键不得当 0。

```bash
python3 scripts/cleaning_tool.py keys subjects.csv measurements.csv \
  --left-key subject_id --right-key subject_code > key_audit.json
```

### 2.3 可逆单位与编码转换（不覆盖原文件）

转换计划含 `plan_version` 和 `operations`；混合单位列使用 `unit_column`，固定单位列使用 `from_unit`。示例：

```json
{"plan_version":"convert-v1","missing_tokens":["","-999"],
 "operations":[{"column":"concentration","unit_column":"unit","to_unit":"μg/L"}]}
```

```bash
python3 scripts/cleaning_tool.py convert convert_plan.json --input data.csv \
  --out /app/output/cleaned_table.csv --audit /app/output/conversion_audit.json
# 已知源编码时显式声明，避免自动猜测：
python3 scripts/cleaning_tool.py convert transcode_plan.json --input legacy.csv \
  --source-encoding gbk --output-encoding utf-8 \
  --out /app/output/transcoded.csv --audit /app/output/transcode_audit.json
```

使用 50 位 `Decimal`；每个非缺失转换逐行验证逆运算数值完全相等，写 `conc__original`、原/目标单位、正逆公式、CSV 行号和输入/输出 SHA-256。原文件不覆盖，未知单位/量纲不符/坏数值失败且不产清洗表。编码自动模式仅严格尝试 UTF/GB18030，**不以 Latin-1 静默吞乱码**；其他编码必须用户提供。当前单位词表限浓度、质量、体积的文档化单位，超范围应新增规则及 bench，不猜比例。

### 2.4 清洗结果可直接下游使用

`cleaned_table.csv` 保留原始键、单位、缺失/排除标志，不把文本强转 numeric、不把日期精度丢失。变更表至少含 `row_locator,field,original_value,action,new_value,rule_id,source`；剔除行另交排除表及理由。质量报告至少给 `rows_before/rows_after, missing_by_field, duplicate_groups, outliers, conversion_count` 和缺失令牌口径。统计假设及图表选择若由任务要求，记录所用行集、变量角色与单位；直方图看分布、箱线图辅助异常定位，不用图遮盖剔除记录。

### 2.5 三道交付机检

```bash
# 1) 原结构/evidence/lineage 存在性
python3 scripts/data_tool.py schema /app/output/result.json
# 2) 可用原始数据表达的 sum/count/mean/min/max 独立复算（相对容差 1e-3）
python3 scripts/data_tool.py recheck /app/output/result.json --csv data.csv
# 3) result 摘要 = quality_report，report 行数/缺失数 = cleaned_table 实算；并复核版本和哈希
python3 scripts/cleaning_tool.py audit /app/output/result.json \
  --cleaned /app/output/cleaned_table.csv --report /app/output/quality_report.json
```

`recheck` 只验证它能表达的数据口径；筛选、跨表、转换或复杂公式必须附同快照复算代码和中间表，不能因 `recheck` 通过就宣称所有清洗正确。任一闸失败先修结果或记录 `issues/partial`，不得手改报告数字迎检。

## 3. 异常处置表

| 题面失败情形 | 识别与动作 | 交付状态/定位 |
|-|-|-|
| 空表/空结果 | 区分真实无记录与筛选/连接错误；保留表头与条件，不补数 | `issues`；筛选项、SQL/代码、0 行日志 |
| 全列缺失 | `plan:ALL_COLUMN_MISSING` 阻断该字段；禁止均值/0 填补 | `partial/issues`；字段名、缺失令牌、全部行范围 |
| 编码乱码/损坏 CSV | 严格解码、NUL/替换符/字段数检查；要求正确编码或新导出，不覆盖源文件 | `partial`；文件名、编码、错误行/错误码 |
| 单位不明/量纲不同 | `plan` 提问、`convert` 失败且不写出；附候选单位但不自行选择 | `unchecked`；字段、原单位文本、待确认问题 |
| 主键空/重复/跨表值冲突 | `keys` 给归一键及两侧行号；裁决前禁止连接膨胀和静默去重 | `issues`；`key_audit.json`、保留规则 |
| 缺失/未检测/<LOD/真0混排 | 分令牌标记并分别计数；按 workorder 处理，不自动插补 | 字段规则、行级变更、敏感性/限制 |
| 异常真实高值或录入失误不明 | 物理限+IQR 双证据；保留原值，剔除/盖帽须明确依据 | `uncertainty` + 原行定位 |
| 文件权限不足/数据库连接失败 | 记录最小必要权限、表/列、查询和系统错误；尝试合法只读导出，仍失败则降级 | `partial/failed`；`unchecked`，不伪造结果 |
| 报告与结果对不上 | `audit` 阻断；从清洗表重算，保留旧值、修正值及原因 | `change_log` 双值与规则版本 |

## 4. result.json 可核验契约（示意字段，数值须替换为实际运行值）

在原案例字段之外保留/补齐以下字段；不把未知填成 0，增益无公平对照则 `gain` 各值为 `null` 并说明未测。

```json
{
 "case_id":"实际case_id", "status":"issues",
 "questions":[{"id":"Q1","answer":"实际答案","evidence":["quality_report.json:missing_by_field.value","cleaned_table.csv:line 3"]}],
 "aggregates":[{"column":"value","op":"count","value":3,"group_by":null}],
 "data_dictionary":{"value":{"semantic":"浓度","unit":"mg/L","source":"dictionary.fields.value"}},
 "lineage":{"snapshot":"实际快照ID","tables":["data.csv"],"filters":[],"join_keys":[],
   "inputs":[{"path":"/input/data.csv","sha256":"实际64位SHA256"}]},
 "run":{"skill_version":"3.0.0","tool_version":"3.0.0","ruleset_version":"rules-v1","dictionary_version":"dict-v1",
   "python_version":"实际platform.python_version()","started_at":"实际UTC时间","random_seed":0},
 "gain":{"baseline_accuracy":null,"skill_accuracy":null,"rework_rounds_saved":null},
 "rule_trace":[{"field":"sample_id","rule":"retain original identifier","rationale":"行级血缘","source":"dictionary.fields.sample_id"},
   {"field":"value","rule":"blank remains missing","rationale":"未检测不等于0","source":"dictionary.fields.value.missing_tokens"}],
 "row_changes":[{"row_locator":"data.csv:3","field":"value","original_value":"","action":"flag","new_value":null,"rule_id":"value.missing","source":"workorder:S2"}],
 "quality_summary":{"rows_before":4,"rows_after":3,"missing_by_field":{"value":1},"duplicate_groups":1,"outliers":0,"conversion_count":0},
 "conversion_audit":{"path":"/app/output/conversion_audit.json","plan_version":"convert-v1"},
 "artifacts":[{"path":"/app/output/cleaned_table.csv","sha256":"实际64位SHA256","type":"cleaned_table"}],
 "unchecked":[],"sources":["/input/data.csv","/input/dictionary.json"],"uncertainty":[],"change_log":[]
}
```

`quality_report.json` 复制同一 `case_id/snapshot` 与 `quality_summary` 数字，并加 `report_version` 和 `missing_tokens_by_field`。所有 `inputs/artifacts` 路径指向真实文件且哈希匹配；版本与时间来自运行，不能写虚构分数或工具状态。

## 5. 最小调用与自测

合成样例只需 `dictionary.json + data.csv` 即可依次跑 `profile → plan → keys（有跨表时）→ convert（有转换时）→ schema/recheck/audit`。示例输出见上述字段，**均非正式案例答案**。维护或验收运行：

```bash
python3 bench/bench_run.py   # 当前 29/29；含每新命令正向零误杀及 blocker/篡改变异必命中
```

适用边界：当前自动转换仅 CSV 和列出的线性单位；Excel/数据库先无损导出并保存查询/表版本；不宣称覆盖任意专有生信格式。基础 Agent 可通用清洗，本 Skill 的增量边界是**字段策略、跨表键冲突、逆变换证据及三方数字对账均可执行检查**；并非声称已获平台对照增益。
