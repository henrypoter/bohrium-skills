# 实验方案设计总课题模板

> 先选当前触发行，再填相应分表；未触发分表不伪造内容。示例值不得复制到正式结果。

## 0. 分诊与版本（所有任务必填）

- case_id / plan_version / result_schema_version / tool_version：
- input_digest / permissions_digest：
- task SHA-256 / case SHA-256：

| route | primary? | workflow | matched location | verbatim quote | required command/output |
|-|-|-|-|-|-|
| generation/comparison/feasibility/parameter/interpretation | | | task.md#L 或 case pointer | | |

无命中：unsupported + 澄清动作。共同字段：variables(type/operational_definition/unit/range)、controls(confounder_excluded)、steps、resources、parameters、risks(trigger/mitigation/stop_rule)、judgments/evidence、sources、unchecked、uncertainty、expert_confirmation、change_log。

## A. generation

- hypothesis（比较对象、方向、阈值）： 
- 设备/材料/步骤/对照/参数/资源： 
- 量程核验：`params result.json --spec limits.json`。

## B. comparison

- comparison_version：
- 候选：id / plan_version / 同口径 metrics / 证据：

| metric | direction | weight | hard min/max | unit | 来源 |
|-|-|-|-|-|-|
| | | | | | |

命令：`compare comparison_input.json --out comparison.json`。保存 ranking/rejected/recommended/sensitivity；说明每次 ±delta 的 top 是否变化，不能隐去硬拒绝。

## C. feasibility

七类检查恰好一次：假设变量、对照、设备材料、时间成本、参数范围、风险异常、伦理安全；每行 status/target/conclusion/evidence，not_checked reason 或 conditional conditions。

| resource ID | 四态/not_checked | 型号/精度/附件/规格 | 需求/库存/货期 | source location |
|-|-|-|-|-|
| | | | | |

成本：quantity×unit_cost=subtotal，total=Σsubtotal，budget/remaining 真算。样本 required/available/unit/source/storage。排期每步 equipment/labor/wait/turnaround/parallel_group；总工期含最长采购货期。

有条件可行验收条件、责任人、伦理/安全动作。附加十异常逐条写 signal/action/disposition/owner/linked_fields。

## D. parameter

problem：parameters(values/unit)、limits(min/max/step/unit/source)、线性 constraints、responses(direction/weight/unit/model/acceptable)、costs(time_hours/money/samples,max/model)、search(max_evaluations)。

响应定义：measurement_method / acceptable_variation / model_ref / uncertainty(method,value) / evidence。运行：

```bash
python3 scripts/exp_tool.py optimize problem.json --out optimization.json
python3 scripts/exp_tool.py replay problem.json result.json
python3 scripts/exp_tool.py params result.json --spec problem.json
```

保存所有 feasible/rejected、拒绝码、score、Pareto、recommended、evaluated_count、stop_reason。无可行解 recommended=null；不可静默截断。

## E. interpretation

输入：dataset_version / unit / absolute_residual_threshold / observations(id,x,y) / 数据证据。输出 intercept/slope/R²、每点 predicted/residual、MAD、阈值、flagged IDs。

异常动作：核对原始记录和仪器并独立重测；不自动删除、不将拟合当因果。阈值=`max(absolute_residual_threshold,2*MAD)`，严格大于才标异常。

## F. 异常、增益与交付

每个结果覆盖 unsupported_input/tool_error/permission_denied/missing_data/execution_failed；当前路由追加专属异常，所有条目绑定真实字段。

基础 Agent 对照：同 case_id/input_digest/permissions_digest/rubric/repetitions；质量记所需交付段、专属输出、定位判断、异常覆盖；效率无双方真实 telemetry 写 not_measured。

交付：`audit + verify`，以及当前路由所需命令全绿。开发 bench：`python3 bench/bench_run.py`，当前 48/48。
