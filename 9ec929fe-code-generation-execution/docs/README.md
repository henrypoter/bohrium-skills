# 科研代码生成与执行 v2.0.0

## 一次完整调用

输入 `/input/case.json`、`/input/task.md`、实际附件和数据字典；输出 `/app/output/result.json`、分析代码、结果表/图、运行与复算日志。Agent 入口及结果增量契约见根目录 `SKILL.md`。

```bash
TOOL=/skills/weekly-skill/scripts/data_tool.py
python3 "$TOOL" profile /input/data.csv > /app/work/profile.json
# 编写 /app/output/analysis.py 与 result.json 后：
python3 "$TOOL" run /app/output/analysis.py --log /app/output/run-log.json \
  --input /input/data.csv --require /app/output/summary.json --timeout 120 --seed 0 \
  -- /input/data.csv /app/output
python3 "$TOOL" recheck /app/output/result.json --csv /input/data.csv
python3 "$TOOL" schema /app/output/result.json
```

有数据库时：

```bash
python3 "$TOOL" sqlcheck /app/output/result.json --db /input/data.sqlite --timeout 10
```

有聚合图时：

```bash
python3 "$TOOL" chartcheck /app/output/result.json --csv /input/data.csv
```

## 命令接口

| 命令 | 实际动作 | 失败信号 |
|-|-|-|
| `profile CSV` | 严格读表、类型/缺失/重复/异常画像、源哈希 | 空表、坏编码、重复表头 |
| `run CODE.py --log LOG ... -- ARGS` | 子进程真执行，审计环境、种子、包、输入/代码/产物 | 依赖/输入/产物缺失、非零退出、超时 |
| `recheck RESULT --csv CSV` | 按筛选、去重、缺失口径独立复算 9 类指标 | 错值、漏组/多组、脏值、空集、错哈希、溢出 |
| `chartcheck RESULT --csv CSV` | 复算声明的图中系列并核对轴、单位、图注、图件哈希 | 图值/单位/哈希不一致 |
| `sqlcheck RESULT --db DB` | 只读 SQLite 实跑，逐单元格比较 | SQL 失败、非 SELECT、错列/行/值、超 10000 行 |
| `schema RESULT` | 版本、证据定位、覆盖状态、增益公平性机检 | 缺版本/定位/理由/对照声明 |

所有工具仅 Python 3.10+ 标准库（当前自测 Python 3.12.4），输出单个 JSON；`0` 通过，`1` 校验失败，`2` 调用错误。`run` 可透传子进程退出码及 `124` 超时；同名日志拒绝覆盖，每次重试改用新文件名。工具不安装依赖、不联网、不绕过权限。

## 最小合成示例（非正式案例）

```bash
python3 scripts/data_tool.py schema bench/fixtures/good_result.json
python3 scripts/data_tool.py recheck bench/fixtures/good_result.json \
  --csv bench/fixtures/sample_data.csv
```

示例中 treat 均值从 `12.5/13.1` 复算；control 的 `-999` 仅在明确声明 `missing_values` 后排除，S07 的单位不自动换算。

## 模板与复用

`templates/data_dictionary.md` 提供字段映射、清洗/聚合声明、SQL 基数检查、运行与结果证据模板。完整异常处置表、增益协议与边界见 `SKILL.md`。

## Bench

```bash
python3 bench/bench_run.py
```

每个命令均含正向零误杀与变异必命中；覆盖数值篡改、脏值、缺列、漏组、空结果、溢出、图件篡改、依赖缺失、非零退出、超时、DML、无证据/版本等。确切通过数以 `REVISION.md` 和实际命令输出为准。Bench 是合成单元测试，不是平台固定案例成绩。

## 已知边界

单文件 CSV 复算支持等值筛选；复杂转换应固化成带输入哈希的派生 CSV。SQL 自动核验仅 SQLite，散点逐点/像素级视觉一致性未自动化，必须在 `coverage`/`unchecked` 诚实标注。平台基础 Agent 原生对照未提供时，增益写 `not_checked`，不填估计数。
