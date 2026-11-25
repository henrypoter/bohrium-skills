# 参数优化交付模板

> 空白字段来自当前案例；缺失写 `not_checked + reason`，不要复制示例数值。

## A. 版本与原文证据

- case_id / plan_version / problem_version / result_schema_version / tool_version：
- input_digest / permissions_digest / problem_sha256：
- sources（source_id/version/path/sha256）：
- 每条判断、参数和响应 evidence（source_id/location/quote/sha256）：

## B. 参数可行域反推

| name | unit | device min/max/step/source | material/safety min/max/step/source | derived_min=max(min) | derived_max=min(max) | recommended value | evidence |
|-|-|-|-|-|-|-|-|
| | | | | | | | |

组合约束：id / coefficients / op / value / source；禁止隐式单位换算和安全放宽。

## C. 响应指标

| name | unit | measurement_method | direction | acceptable_min/max | acceptable_variation | model_ref | uncertainty method/value | evidence |
|-|-|-|-|-|-|-|-|-|
| | | | | | | | | |

模型状态：observed / declared surrogate / historical fit；具来源和适用范围，不将 surrogate 写成 observation。

## D. 搜索轨迹

- strategy=exhaustive_grid；domain_size=；max_evaluations=：
- initial_design=all_declared_finite_domain_points：
- 每轮候选索引、计算响应、成本、拒绝原因：
- 可行候选归一化响应、权重、score：
- Pareto_indices 与舍弃理由：
- stopping_rule=`evaluated_count==domain_size`；stop_reason：
- 重放：`python3 scripts/exp_tool.py replay problem.json result.json`。

## E. 成本响应联合权衡

| candidate | response(s) | time_hours/max | money/currency/max | samples/max | 硬约束拒绝码 | score |
|-|-|-|-|-|-|-|
| | | | | | | |

推荐点必须满足所有硬预算。响应牺牲口径：与哪个 Pareto 点比、牺牲多少响应、节省多少成本；权重待确认时列 `expert_confirmation`。

## F. 变量、对照、步骤与风险

变量：name/type/operational_definition/unit/range；对照：purpose/confounder_excluded；步骤绑定设备/材料/参数；风险写 trigger/mitigation/stop_rule。

六类异常必须登记：无可行解、约束冲突、数据缺失、设备报错、指标矛盾、权限不足。每条：code/signal/action/disposition/owner/linked_fields。

## G. 增益与最终自检

- 同 case/input/permissions/rubric 的 baseline 路径与重复次数：
- 质量：交付段、定位判断、异常覆盖、可行推荐（baseline vs Skill）：
- 效率：runtime、筛选返工、改参返工；无 telemetry 写 not_measured。
- unchecked/uncertainty/expert_confirmation/change_log：

交付前运行 `optimize → replay → params → audit → verify`。开发自测 `python3 bench/bench_run.py`，当前基线 33/33。
