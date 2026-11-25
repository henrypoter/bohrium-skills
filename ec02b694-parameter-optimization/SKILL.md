---
name: parameter-optimization
description: 有限参数域的约束感知优化；真实穷举设备材料安全交集、响应与成本联合权衡、Pareto/停止判据、完整重放、异常绑定和逐字证据。
---

# 实验参数优化建议

## 用途与边界

读取实际 `/input/case.json`、`/input/task.md`、设备/材料/安全限制、历史数据和 prospective resource/price/booking contracts，输出可执行参数、可行区间、响应口径、搜索轨迹、成本预算与风险。适用于**已声明有限参数域和可计算响应/成本模型**的任务。模型预测必须标为 surrogate/prediction，不能冒充实测；不能从论文题名或领域标签发明响应关系。

不擅自做单位换算，不绕开安全阈值，不把不完整网格说成“收敛”，不把线性代理当普适科学规律。数据不足写 `not_checked`；无可行解返回 `recommended=null`。无第三方依赖，Python 3.8+ 标准库。

## 版本、证据与交付

`/app/output/result.json` 保留原 `output_contract` 字段和 `case_id`，并增加：

- `result_schema_version=parameter-result-3.0.0`、`tool_version=parameter-exp-tool-3.0.0`、独立 `plan_version`。
- 实际规范化输入/权限清单的 `input_digest/permissions_digest`。
- `response_metrics / search / cost_budget / optimization / exception_register`。
- `sources[]`：`source_id/version/path/sha256`；判断、参数、响应定义的 `evidence[]`：`source_id/location/quote/sha256`。JSON Pointer 值必须等于 quote；文本 quote 必须逐字存在。PDF新增字段仍需真实提取文本/`text_path` 和页码，不能凭标签引用。

先写诚实的 partial，再执行完整闭环：

```bash
S=/skills/weekly-skill/scripts/exp_tool.py
P=/app/work/problem.json
R=/app/output/result.json
python3 "$S" optimize "$P" --out /app/work/optimization.json
# 将完整 optimization 对象嵌入 result.json 的 optimization 字段
python3 "$S" replay "$P" "$R"
python3 "$S" params "$R" --spec "$P"
python3 "$S" audit "$R"
python3 "$S" verify "$R" --source-root /app/work/source_snapshot
python3 "$S" schema "$R"
```

`optimize` 返回 1 且产物 `status=no_feasible_solution` 是完整执行后的合法“无可行解”；输入错误/网格超预算返回 2，不得静默截断。

## 一、把材料变成可机检 problem.json

最小接口如下，所有数值必须有限；`source` 指向真实字段定位：

```json
{
 "problem_version":"v1",
 "parameters":{"temperature":{"values":[40,50,60],"unit":"C"},"duration":{"values":[1,2],"unit":"h"}},
 "limits":{
   "temperature":{"min":40,"max":60,"step":10,"unit":"C","source":"设备清单#/temperature"},
   "duration":{"min":1,"max":2,"step":1,"unit":"h","source":"SOP#/duration"}
 },
 "constraints":[{"id":"load","coefficients":{"temperature":1,"duration":10},"op":"<=","value":75,"source":"通量表#/row3"}],
 "responses":{
   "yield":{"direction":"maximize","weight":0.7,"unit":"%","acceptable_min":50,
            "model":{"intercept":20,"coefficients":{"temperature":0.6,"duration":2}}},
   "impurity":{"direction":"minimize","weight":0.3,"unit":"%","acceptable_max":15,
               "model":{"intercept":5,"coefficients":{"temperature":0.1,"duration":0.5}}}
 },
 "costs":{
   "time_hours":{"max":5,"model":{"intercept":1,"coefficients":{"temperature":0.02,"duration":0.5}}},
   "money":{"max":60,"model":{"intercept":20,"coefficients":{"temperature":0.5,"duration":5}}},
   "samples":{"max":6,"model":{"intercept":3,"coefficients":{}}}
 },
 "search":{"strategy":"exhaustive_grid","max_evaluations":20}
}
```

线性模型只是当前工具支持的可复核形式；系数必须来自实际输入/已声明代理模型。初始设计=全部有限域点；后续轮次=完整网格后无，停止条件=`evaluated_count==domain_size`。需要贝叶斯优化、连续变量、随机拟合时，本工具声明不适用并转专用流程，不冒充实现了这些能力。

## 二、真实搜索、联合权衡和停止判据

`optimize` 用 Decimal 完整笛卡尔积：

1. 逐点检查参数上下限、步进、显式线性互斥/组合约束。
2. 计算声明模型响应，执行 `acceptable_min/max`；模型输出统一标 `explicit_declared_models_not_measurements`。
3. 同点计算机时、费用、样本数，任何硬预算超限即拒绝，保留 `rejection_reasons`。
4. 只在可行候选内按响应方向做 min-max desirability；常数响应记 1，权重归一化计算 score。
5. 用全部响应方向和三项成本最小化计算 Pareto 集；确定排序为 score 降序、参数 canonical JSON 升序。
6. 保留每条可行和拒绝记录，完整结束才可 `exhaustive_grid_complete`；即使无可行解也报告真实 domain_size 和逐项拒绝码。

推荐值不得直接抄“经验最优”：它必须等于 `optimization.feasible_candidates[0]`；`replay` 从 problem 重算并与整对象比较，包括拒绝轨迹、Pareto、推荐、成本及停止原因。权重是决策偏好不是科学事实；权重未由题面给定时列为专家确认，并展示 Pareto，而不是隐藏取舍。

## 三、量程反推和响应/成本口径

- 每个 `parameters[]` 写 `name/value/unit/derived_min/derived_max/evidence`。`params` 对同名多条限制取 `max(min)`、`min(max)`，核对推荐值、步进和单位；不支持的单位组合直接报错。
- 每个 `response_metrics[]` 必须有 `name/unit/measurement_method/direction/acceptable_variation/model_ref/uncertainty{method,value}/evidence`。没有不确定度依据就标 `not_checked`，不能写“高精度”。
- `search` 记 `strategy/initial_design/rounds/stopping_rule/stop_reason/evaluated_count/tradeoff`，并与 optimization 一致。
- `cost_budget` 同时写币种、费用预算、机时预算、样本预算及推荐点实际三项成本；费用、机时、样本与推荐候选不一致即机检失败。必须说清成本受限时响应牺牲多少，或证明推荐点仍为 Pareto 可选。

## 四、风险与异常处置表（逐条机检）

`exception_register` 每条必须有 `code/signal/action/disposition/owner/linked_fields`，`disposition=downgrade|label|manual|stop`。下列六条恰好一次，且风险条另有 trigger/mitigation/stop_rule：

| code / 点名失败情形 | 识别信号 | 具体动作与绑定 |
|-|-|-|
| `no_feasible_solution` 无可行解 | 完整枚举后 feasible_count=0 | recommended=null；按约束/响应/预算拒绝码列放宽方向，转人工；绑定 feasible_count/rejected_candidates |
| `conflicting_constraints` 约束冲突 | min>max、单位不一致、目标温度超材料耐温或交集为空 | 停止搜索，列冲突字段，禁止自动放宽；绑定 parameters/rejected_candidates |
| `missing_data` 数据缺失 | 参数域、限值、响应模型或不确定度缺失 | 受影响预测 `not_checked`，保留可算部分并降级；绑定 response_metrics/optimization |
| `equipment_error` 设备报错 | fault、实际设定失败或校准过期 | 冻结候选，选择未拒绝下一点并重放；无替代则停止；绑定 parameters/search |
| `conflicting_metrics` 指标互相矛盾 | 指标方向/单位冲突，或一个改善另一个越硬阈值 | 不报伪单一最优，展示 Pareto 并确认权重；绑定 response_metrics/pareto_indices |
| `insufficient_permissions` 权限不足 | 原始数据或设备访问 permission denied | 停止越权动作，保留已有哈希，标 failed/not_checked 并交管理员；绑定 status/unchecked |

## 五、同输入基础 Agent vs 本 Skill

无平台基线时 `gain.status=not_run+reason`。存在同权限基线时执行：

```bash
python3 "$S" gain /app/work/baseline_result.json "$R" --out /app/output/result_with_gain.json
```

命令拒绝不同 `case_id/input_digest/permissions_digest`。质量字段实测十项交付段、带定位判断、六异常覆盖、是否有可行推荐；效率只有双方已有同口径 `telemetry` 才记筛选返工、人工改参返工轮次和 runtime，否则 `not_measured`。单次 pair 为 `repetitions=1`，正式三次重复保存三份独立记录；不得复制或估算榜首/基线成绩。

## 六、结果骨架与完整完成标准

```json
{
 "case_id":"","status":"issues","plan_version":"v1",
 "result_schema_version":"parameter-result-3.0.0","tool_version":"parameter-exp-tool-3.0.0",
 "input_digest":"64-hex","permissions_digest":"64-hex",
 "research_goal":{},"variables":[],"controls":[],"steps":[],"resources":{},"parameters":[],
 "response_metrics":[],"search":{},"cost_budget":{},"optimization":{},
 "risks":[],"judgments":[],"expert_confirmation":[],"unchecked":[],"sources":[],"uncertainty":[],"change_log":[],
 "exception_register":[],
 "gain":{"status":"not_run","reason":"","design":{"same_case_id":"","same_input_digest":"","same_permissions":true,"repetitions":1},"quality":{},"efficiency":{}}
}
```

完成标准不是参数表长，而是：推荐落在反推交集；响应有测量和不确定度口径；成本与单位一致；搜索轨迹可重放；停止确有依据；失败有处置；假设、对照、设备、时间、风险和专家确认仍保留。`bench/fixtures/` 提供合成最小输入、problem、optimization 和 result，均非正式答案。

## 自检

```bash
python3 /skills/weekly-skill/bench/bench_run.py
```

bench 对每个命令做正向与变异测试，覆盖最优选择、预算裁剪、无可行解、网格上限、NaN、重放篡改、停止条件、证据与公平对照。bench 通过不替代正式科学验证；高维组合爆炸、非线性响应、约束在线变化和真实设备故障仍需物理世界/专家验证。
