# 修订说明：科研代码生成与执行 v2.0.0

## 本轮变更范围

只修改本提交目录：`SKILL.md`、`REVISION.md`、`scripts/data_tool.py`、`bench/bench_run.py`、`bench/fixtures/good_result.json`、`docs/README.md`、`templates/data_dictionary.md`。`sample_data.csv` 与 `GITHUB_URL.txt` 保持原样；未改共享核心、未提交或 push。示例均标明合成、非正式答案。

## 实际效果（40）

- **真实闭环**：新增 `run`，以子进程真实执行分析代码，记录命令、退出码、stdout/stderr、超时、种子、Python/平台、声明依赖版本、代码/输入/产物 SHA256 和必需产物检查。Bench 的成功、退出码 3、缺产物、缺输入、依赖缺失、超时均真跑，不是状态自述。
- **数值真复算**：`recheck` 由旧版 5 种基础运算升级为 `sum/count/row_count/mean/min/max/median/stdev/sem` 9 种口径，并支持等值筛选、单/多列分组、显式缺失哨兵、按键去重、严容差、源 SHA256。漏组/多组、非法数值静默排除、空声明、错误快照和溢出均硬失败。
- **图表逐项对数**：新增 `chartcheck`，逐项重算图内声明系列，并检查轴标目、必需单位、图注、图例字段与图件哈希；图值和图件篡改测试均命中。
- **数据库真重跑**：新增 `sqlcheck`，SQLite 只读执行 SELECT/WITH，逐列/逐行/逐单元格核对，记录数据库/结果哈希与空结果；非 SELECT 拒绝，错误 SQL 保留原因。
- **可核验版本与定位**：`result.json` 强制 `schema_version/skill_version=2.0.0`、输入快照哈希、覆盖状态、实际命令；结论证据强制 `artifact/location + quote或sha256`。五项未执行环节必须明确 `not_checked + reason`。
- **可复用实例**：发布夹具 `good_result.json` 自身必须通过 `schema` 和 `recheck`，避免文档示例与校验器脱节。

## 使用增益（25）

`gain` 固定 `protocol_version/same_input/same_permissions` 和 `baseline/skill` 两臂。每臂必须含质量、效率、证据：正确结论比例、首次执行成功率、真实返工、人工改数/核对、墙钟与 trace/log。已测状态必须给证据；平台未提供原生基础臂时明确 `not_checked`、差值 `null`。相对基础 Agent 的价值不是生成更多代码，而是**执行前置检查 + 独立重算 + 变异证据**；不把仓内 Bench 当平台增益。

## 创新增益（15）

1. **运行证明 manifest**：执行退出、超时和依赖失败与产物哈希同处一份日志；无产物不能“成功”。
2. **分析口径即复核程序**：筛选、缺失、去重、分组直接成为独立复算输入，避免报告代码与复算代码各说一套。
3. **静默失败显式化**：未声明脏数不被当缺失，分组集合做双向完备比较，空查询标 `empty_result`，错误快照与数值溢出失败。

边界：复算自动覆盖单 CSV 的等值筛选与已支持聚合；复杂转换须留痕派生 CSV；SQL 自动复跑仅 SQLite、最多 10000 行；图检查覆盖已声明聚合系列，不冒充散点逐点/像素级视觉核验。基础 Agent 可以手写同类逻辑，本 Skill 的增益在于统一、可执行、可变异验证的硬门槛。

## 可靠体验（10）

异常表逐条覆盖缺列、类型不符、依赖缺失、查询为空、查询失败、数值溢出、权限不足，并补路径/编码/内存/超时、缺失/异常/重复、连接膨胀、图数不符、材料缺失与无法解释。每行有识别信号和停止、降级、标注或交人工动作，未用“注意”代替处置。

## 生态贡献（10）

保留 9 个 UTF-8 文本资源：入口、说明、模板、单文件标准库工具、合成输入/结果、GitHub 文件和 Bench。模板包含字段映射、清洗与 SQL 基数、图系列、证据和对照清单。全部新命令只依赖 Python 标准库。

## 可复跑 Bench 证据

执行：

```bash
cd week4-road2-q4/submission
python3 -m py_compile scripts/data_tool.py bench/bench_run.py
python3 bench/bench_run.py
```

本轮最终结果：**38/38 PASS**（不改变正式平台得分）。覆盖 `profile` 6 项、`recheck` 8 项、`chartcheck` 4 项、`run` 7 项、`sqlcheck` 5 项、`schema` 7 项，加发布夹具 1 项。运行日志同名覆盖也已纳入变异测试，确保每次尝试独立留痕。

## 距仍需平台验证的部分

- 尚未获得官方 3 案例 × 3 重复的原生 trace、基础 Agent 同权对照、金标准和榜首分，因此不能声称已验证官方准确率、效率增益或榜首差距数值。
- Excel/非 SQLite 驱动需要现场 `resources.yaml` 中工具；标准库复算器不声称原生支持这些格式。
- 聚合图系列可自动对数；复杂原始点图、统计显著性图元和视觉渲染仍需任务代码及人工核验，已写入适用边界。
- GitHub 文件保持既有 URL；本轮按要求未 push，未重新验证公开链接内容是否与本地 v2.0.0 同步。
