---
name: code-generation-execution
description: 科研代码生成与执行：真实运行分析/SQL，保留版本与失败现场，并从原始 CSV/SQLite 独立复算数值和图表系列
---

# 科研代码生成与执行

目标是闭环 **读字典 → 显式清洗口径 → 生成代码 → 真执行 → 独立复算 → 交付**。不是只给代码框架。所有机检工具仅用 Python 标准库；生成正式案例答案、伪日志或估计增益均禁止。

不适用：实验设计、因果/机理创新、论文写作。正式输入为 `/input/case.json`、`/input/task.md` 及其实际附件；先读 `environment/resources.yaml` 和原任务的 `output_contract`。固定案例名称只用于识别数据形态，不得代替现场读数。

## 输入、输出与工具

- 工作区 `/app/work`；最终 `/app/output/result.json`、可编辑分析代码、清洗表、数值表、图件（任务要求时）、日志与真实预览。
- 保留原 `output_contract` **全部字段、字段名与嵌套结构**，以下字段只做增量补充。
- 工具位于 `/skills/weekly-skill/scripts/data_tool.py`；示例中的相对路径以提交根目录为工作目录。
- `schema_version` / `skill_version` 当前均为 `2.0.0`。

## 执行闭环（按顺序）

### 1. 快照、字典、字段对齐

读取数据字典的字段含义、单位、编码值、缺失哨兵、主键、允许范围。CSV 先运行：

```bash
python3 /skills/weekly-skill/scripts/data_tool.py profile /input/data.csv > /app/work/profile.json
```

将 `sha256` 写入 `lineage.source_sha256` 和 `sources[]`。画像含行列、编码、缺失、完全重复、脏数值、IQR 异常及量级告警。**画像告警不是自动清洗许可**：只有字典或题面明确时才把 `-999` 等列为 `missing_values`，只有明确主键/重复规则时才 `drop_duplicates`。Excel/其他格式按已提供工具转换，并同时保存原文件与转换 CSV 的哈希；转换失败标 `partial`，不得假装已读。

### 2. 把口径写进机器可执行声明

每个分析数字在 `aggregates[]` 声明 `id/column/op/value`，支持 `sum/count/row_count/mean/min/max/median/stdev/sem`。按需增加：

- `where: {"group":"treat"}`：精确等值筛选；复杂筛选须在可执行代码中生成带血缘的派生 CSV，再对派生表复算。
- `group_by: "group"` 或列名数组：`value` 必须是覆盖所有实际组的对象，漏组、虚拟组都会失败。
- `missing_values: ["", "-999"]`：仅显式列出的值排除；其他非法数值直接失败，不静默丢弃。
- `drop_duplicates: true` 或键列数组：去重范围与保留首条规则必须同时写入 `change_log`。
- `tolerance`：默认绝对/相对容差均 `1e-9`，不能用宽容差掩盖错误。

每个 `stdev/sem` 至少两个有效值；空集、非法列、非有限数、溢出均失败。\"显著\"必须有实际检验、方法、统计量、自由度和 p 值；假设未检查就写 `not_checked`，不得只报 p。无需统计推断的纯描述任务不得虚增检验。

### 3. 真执行并记录失败现场

将真实分析保存为 `/app/output/analysis.py`，然后用审计执行器运行，而不是声称运行过：

```bash
python3 /skills/weekly-skill/scripts/data_tool.py run /app/output/analysis.py \
  --log /app/output/run-log.json --input /input/data.csv \
  --require /app/output/cleaned.csv --require /app/output/summary.json \
  --timeout 120 --seed 0 --package numpy -- /input/data.csv /app/output
```

仅声明代码实际导入的 `--package`；纯标准库代码不写该参数。执行器前置检查依赖，记录命令、代码/输入/产物 SHA256、Python/平台/包版本、种子、stdout/stderr、墙钟、退出码、超时与必需产物。**每次尝试使用新日志名（run-log-01/02/...）；同名日志拒绝覆盖，保留每次失败现场。** 随机算法还需在代码内 `random.seed` 或传入对应库种子。未使用包不得编造版本。需要隔离时使用标准库 `python3 -m venv /app/work/venv`；无权限或依赖无法取得时降级到已提供环境并保留真实失败，不进行未许可网络安装。

### 4. 独立复算数值、查询与图

```bash
python3 /skills/weekly-skill/scripts/data_tool.py recheck /app/output/result.json --csv /input/data.csv
python3 /skills/weekly-skill/scripts/data_tool.py chartcheck /app/output/result.json --csv /input/data.csv
python3 /skills/weekly-skill/scripts/data_tool.py sqlcheck /app/output/result.json --db /input/data.sqlite
```

- **recheck** 从源行按显式口径重算，不信任 `analysis.py` 的中间值；先验证输入 SHA256。
- **有图才运行 chartcheck**：`figures[]` 每项必须有 `path/sha256/axes/legend/caption/series[]`。每个 `series` 使用与 `aggregates` 相同的复算格式，图中均值、和、极值、误差（`stdev/sem`）逐项对源数据；无图例时 `legend: []`。散点逐点映射不在本工具边界内，须另交付散点数据表与生成代码，并在 `unchecked` 如实标明未自动核验的部分。
- **有数据库才运行 sqlcheck**：`queries[]` 每项写 `id/sql/columns/rows`。工具用 SQLite `mode=ro` 实跑，只接受 `SELECT/WITH`，逐列、逐行、逐单元格核对并记录结果哈希与空结果；空结果可为合法通过，但必须显式 `empty_result`。连接漏条件/基数膨胀先在 SQL 前后比较原表、连接后行数和主键去重数。
- 不要求的环节在 `coverage` 标 `not_checked` 并给原因；要求但失败的不能伪装 `not_checked`，状态须 `partial/issues/failed`。

### 5. 先保存诚实部分，再最终验收

先写保留原合同字段的部分 `result.json`，随后逐步补全。最终：

```bash
python3 /skills/weekly-skill/scripts/data_tool.py schema /app/output/result.json
```

`questions[].evidence[]` 必须是对象：`artifact + location + (quote 或 sha256)`。文本结论用原文逐字 `quote` 和精确句/页/段定位；数据结论用字段/行/筛选定位和源哈希。`coverage` 固定覆盖 `cleaning/statistics/visualization/execution/query`，每项只能 `pass/issues/not_checked`，未检必须写理由。所有产物需可读路径与哈希；失败保留日志，不删除报错。

## result.json 增量契约模板（示意，不是正式答案）

```json
{
  "schema_version":"2.0.0", "skill_version":"2.0.0", "case_id":"",
  "status":"pass|issues|partial|failed",
  "questions":[{"id":"Q1","answer":"","evidence":[{"artifact":"data.csv","location":"column=x; rows=1-2","quote":"原始逐字行","sha256":"64位小写hex"}]}],
  "aggregates":[{"id":"a1","column":"value","op":"mean","value":0,"where":{},"missing_values":[""]}],
  "figures":[], "queries":[], "runs":[{"path":"/app/output/run-log.json","sha256":"64位小写hex"}],
  "coverage":{"cleaning":{"status":"pass"},"statistics":{"status":"pass"},"visualization":{"status":"not_checked","reason":"任务未要求"},"execution":{"status":"pass"},"query":{"status":"not_checked","reason":"无数据库"}},
  "data_dictionary":{"value":"含义、单位、缺失编码"},
  "lineage":{"snapshot":"现场版本/哈希","tables":["data.csv"],"filters":[],"join_keys":[],"source_sha256":"64位小写hex","command":"实际执行命令"},
  "gain":{"protocol_version":"1.0.0","same_input":true,"same_permissions":true,
    "baseline":{"status":"measured|not_checked","quality":{"accuracy":null},"efficiency":{"rework_rounds":null,"manual_checks":null},"evidence":[]},
    "skill":{"status":"measured|not_checked","quality":{"recheck_passed":null},"efficiency":{"rework_rounds":null,"manual_checks":null},"evidence":[]},
    "quality_delta":null,"efficiency_delta":null},
  "unchecked":[], "sources":[{"path":"data.csv","sha256":"64位小写hex"}],
  "uncertainty":[], "change_log":[]
}
```

## 基础 Agent vs 本 Skill 公平对照

同一原始输入哈希、任务文本、权限、解释器/资源、模型预算、随机种子分别运行两臂；禁止给 Skill 额外字典或人工答案。逐臂记录：正确结论数/总结论数、首次执行成功率、真实返工轮次、人工改数/核对条数、墙钟，以及对应原生 trace/log 路径。平台未提供基础臂时 `baseline.status=not_checked`、差值 `null`，不能把本仓 bench 或主观判断写成官方增益。仓内变异测试只证明校验器能抓错。

## 异常处置表（识别信号 → 具体动作）

| 题面失败情形 | 识别信号 | 降级/标注/终止动作 |
|-|-|-|
| 缺列/字段名不匹配 | `recheck` 报聚合/分组/筛选缺列 | 停止该结论；回字典核对，若仅改名则映射写入 `change_log`；仍有歧义列两种口径，`unchecked` 交人工 |
| 类型不符/编码混乱 | 非缺失脏数值、CSV 解码/重复表头错误 | 不把脏值当 0 或缺失；定位列与原值，转换失败标 `partial` |
| 缺失/异常值/重复 | profile 缺失、IQR、重复告警 | 按显式规则排除/去重，报告前后行数与排除数；无字典依据只标记，不自动改值 |
| 依赖缺失/包写法不兼容 | `dependency_missing`、ImportError/AttributeError 与真实退出码 | 前置终止或按 `resources.yaml` 用已装版本改写；记录包版本与替代，不伪造成功 |
| 查询为空 | `empty_result=true` | 与预期空集区分；逐条去掉一个筛选做诊断（不改正式答案），保留行数，无法解释则 `unchecked` |
| 查询失败/连接膨胀 | SQLite 错误；连接后行数或主键重复异常 | 只读重跑定位 SQL/键；修正后完整复算，失败则 `partial`，不得填估值 |
| 数值溢出/非有限数 | recheck `overflow`、NaN/inf、进程异常 | 终止受影响的均值/方差等，检查单位与算法后重跑；仍溢出交人工 |
| 权限不足 | OSError/SQLite readonly/目录不可写 | 不绕过权限；改 `/app/work` 或 `/app/output` 合法路径，数据库只读；输入不可读则 `partial/failed` |
| 路径/内存/超时 | FileNotFoundError、MemoryError、run timed_out | 用输入实路径与分块/预聚合降级；超时日志原样保留，未产出的结论标 `not_checked` |
| 图表与源数据不符 | chartcheck 数值、单位、图件 SHA256 不一致 | 撤回图件或重生成后复跑；不散补数值，余下人工检查写 `unchecked` |
| 无法解释结果/材料缺失 | 字典冲突、无来源、金标准不可得 | 分别写 `uncertainty` 与 `unchecked`；标 `issues/partial`，不交人工猜测值 |

## 适用边界与最小自测

复算器当前支持单张 CSV、等值筛选、精确去重和上述聚合；其他格式先留痕转换。`sqlcheck` 面向 SQLite 只读查询，最多返回 10000 行；其他数据库先由已提供驱动导出结果并保留原生查询日志，不能声称已自动核验。`chartcheck` 核验已声明系列，不替换视觉检查或原始逐点图核验。

```bash
python3 bench/bench_run.py
```

完整正向/变异回归结果见 `REVISION.md`。`bench/fixtures` 全部为合成最小示例，不是三个正式案例的预制答案。
