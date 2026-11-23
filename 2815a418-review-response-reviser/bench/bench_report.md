# bench 报告（确定性自测与对照）

> 夹具全部自拟，非正式案例、非预制答案。复跑：`python3 bench/bench_run.py`，全部断言通过 exit 0，否则 exit 1。

## 自测断言

| 断言 | 结果 | 明细 |
|---|---|---|
| 解析:中文意见条数=3 | PASS | items=3 subs=3 mismatch=0 |
| 回归:直双引号顺序配对,无误报误解 | PASS | mismatch=0（夹具两处引文均在基线中） |
| 回归:Major/Minor comment 解析=3条 | PASS | ids=['R1.1', 'R1.2', 'R2.1'] |
| 正向:好样例 verify exit=0 | PASS | status=pass fail=0 warn=0 |
| 正向:跨行锚点命中并回填行号 | PASS | locs=[{'anchor': '仅基于 1000 条数据、未报告方差', 'line': 8, 'heading': '结果'}, {'anchor': '在 1000 条随机数据上平均耗时 12 ms', 'line': 3, 'heading': '摘要'}, {'anchor': '采样比例为 5%', 'line': 6, 'heading': '方法'}] |
| 变异:漏回意见->coverage fail | PASS | exit=1 |
| 变异:虚构锚点->location fail | PASS | exit=1 |
| 变异:反驳缺缓冲语->rebuttal fail | PASS | exit=1 |
| 变异:只回R1.10->R1.1 coverage fail(编号边界) | PASS | exit=1 |
| 对照:手工信被核查出缺陷(exit=1) | PASS | coverage=67% anchor=50% |
| 对照:matrix/trace 正常产出 | PASS | matrix rows=3 -> /tmp/tmp3o8eo5km/matrix.md \| diff lines=14 -> /tmp/tmp3o8eo5km/changes.diff |

## 公平对照（同一稿件/同一意见/同一核查脚本）

| 指标 | 手工路径（无矩阵/无机器核验） | 本流程确定性路径 |
|---|---|---|
| 意见覆盖率（机器核查） | 67% | 100% |
| 锚点核验率（located/claims） | 50% | 100% |
| 机器可复核产物数 | 0 | 5（解析/锚点表/矩阵/核查报告/diff） |
| 确定性路径耗时 | —（人工逐条比对 3 条意见×锚点） | 1.14 秒 |

## 边界声明（诚实范围）

- 只度量确定性可机核指标，不代表 LLM 端到端写作质量
- 手工信为自拟模拟基线，非基础 Agent 实测输出
- 夹具为短材料，长稿件/多轮返修的端到端结论以平台 harness 为准

总体：11/11 断言通过，exit 0。
