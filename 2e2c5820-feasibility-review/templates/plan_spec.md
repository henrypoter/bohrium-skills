# 版本化可行性审查模板

> 本模板是字段清单，不是答案。所有事实必须来自当前案例；未知填 `not_checked + reason`。

## A. 版本与证据

- case_id / plan_version / result_schema_version / tool_version：
- input_digest / permissions_digest（64 位 SHA-256）：
- sources：source_id / version / path / sha256 / text_path（需要时）
- 每条 evidence：source_id / location / quote / sha256

## B. 七类检查（每类恰好一次）

| category | status | target | conclusion / not_checked reason | conditions | evidence |
|-|-|-|-|-|-|
| 假设与变量 | | | | | |
| 对照组 | | | | | |
| 设备材料 | | | | | |
| 时间成本 | | | | | |
| 参数范围 | | | | | |
| 风险与异常 | | | | | |
| 伦理与安全 | | | | | |

总体：feasible / conditionally_feasible / infeasible / partial；有条件可行条件必须能验收、有责任人。

## C. 设备、材料与样本

| ID | 类型 | 需求型号/规格/精度/附件 | 清单定位 | available/outsource/purchase/unavailable/not_checked | 数量/货期/保存 | 处置 |
|-|-|-|-|-|-|-|
| | | | | | | |

样本：required / available / unit / source / storage / ethics_ref；缺口=`max(0,required-available)`。

## D. 预算与排期

| cost id | quantity | unit_cost | subtotal=quantity×unit_cost | currency | 来源 |
|-|-|-|-|-|-|
| | | | | | |

total=Σsubtotal；budget=；remaining=budget-total；within_budget=真值。

| step | equipment_hours | labor_hours | wait_hours | turnaround_hours | duration | parallel_group |
|-|-|-|-|-|-|-|
| | | | | | max(equipment,labor)+wait+turnaround | |

`elapsed_hours=max(purchase lead_time_hours)+Σ_group(max step duration)`；deadline 与余量必须实算。

## E. 参数多源可行域

| name | unit | 来源A min/max/step | 来源B min/max/step | derived_min=max(min) | derived_max=min(max) | value | 步进/互斥 | evidence |
|-|-|-|-|-|-|-|-|-|-|
| | | | | | | | | |

机检：`python3 scripts/exp_tool.py params result.json --spec limits.json`。

## F. 异常与审批

至少登记题面六异常（缺页、参数缺失、设备不明、伦理未定、自相矛盾、超长文档）和设备故障、批次差异、样本不足、参数越界。每条写 signal/action/disposition/owner/linked_checks，不得只写“注意”。

| code | signal | action | disposition | owner | linked_checks |
|-|-|-|-|-|-|
| | | | downgrade/label/manual/stop | | |

伦理/安全状态：approved / pending / not_required / not_checked；pending/not_checked 必须给 action 并禁止启动相关步骤。

## G. 基础 Agent 对照与交付

- 同 case_id / input_digest / permissions_digest / rubric / repetitions：
- 质量：七类覆盖、定位判断、异常覆盖（baseline vs Skill）：
- 效率：runtime、返工、补材料轮次；无真实 telemetry 写 not_measured：
- unchecked / uncertainty / expert_confirmation / change_log：

交付前必须 `audit + resources + params + verify` 全绿；运行 `python3 bench/bench_run.py`，当前基线为 33/33。
