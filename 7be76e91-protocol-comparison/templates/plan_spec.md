# 方案比较规格表（比较题）

> 本模板用于从案例材料生成审计字段，不是预制答案。未知填 `unknown`，不可将规划合同称为真实实验室确认。

## 1. 同口径候选矩阵

| 字段 | P-A（版本） | P-B（版本） | P-C（版本） | 来源定位 |
|-|-|-|-|-|
| 可检验假设 |  |  |  |  |
| 变量：类型/操作定义/测量/单位/范围 |  |  |  |  |
| 对照：目的/排除混杂 |  |  |  |  |
| 步骤：设备/材料/依赖/并行 |  |  |  |  |
| 参数：value/unit/min/max/来源 |  |  |  |  |
| 资源：设备/耗材/样本/人员 |  |  |  |  |
| 判读：终点/方向/阈值 |  |  |  |  |
| 风险：触发/后果/缓解/止损/替代 |  |  |  |  |
| 证据：判断/来源 ID/定位 |  |  |  |  |
| 硬约束：设备/材料/预算/时间/参数 | pass/fail/unknown | pass/fail/unknown | pass/fail/unknown |  |
| 全成本/币种 |  |  |  |  |
| 全周期/时间单位 |  |  |  |  |

不得只填被偏好的方案；缺失字段标 `unknown`，不能删列。候选全部不可行时不得强行选“相对最好”。

## 2. 成本与时间算术

- `capital + machine + consumables + labor + rework = cost_total`；一次性与按次成本分列。
- `preparation + execution + queue + characterization + rework = time_total`。
- 每项有单位与 `source_locator`；若并行，另给关键路径说明，不能简单相加或漏掉排队。

## 3. 选择与敏感性

- 选择：`selected_candidate_id`，只允许选硬约束全为 `pass` 的候选。
- 舍弃：每个未选候选恰好一条具体理由，引用数值、证据或约束。
- 敏感性：`assumption / threshold / effect / evidence`，说明何时翻转；翻转后重验硬约束。
- 全不可行：`selected_candidate_id=null`，`recovery.status=blocked`，给放宽项、替代路径、影响和决策人。

## 4. 风险与异常表

| type | trigger | action | impact | decision_owner | status |
|-|-|-|-|-|-|
| equipment_unavailable |  |  |  |  |  |
| material_unavailable |  |  |  |  |  |
| budget_exceeded |  |  |  |  |  |
| time_window_conflict |  |  |  |  |  |
| parameter_window_conflict |  |  |  |  |  |
| all_candidates_infeasible |  |  |  |  |  |

## 5. 交付闸

```bash
python3 scripts/exp_tool.py schema /app/output/result.json
python3 scripts/exp_tool.py compare /app/output/result.json
python3 scripts/exp_tool.py feasibility /app/output/result.json --spec /app/work/feasibility-spec.json
```

- [ ] 原 `output_contract` 字段和 `case_id/input_id` 保留
- [ ] 所有候选统一字段、独立版本，来源有 `id/version/locator`
- [ ] 成本与时间可重算，单位一致
- [ ] 选择、逐项舍弃、敏感性齐全；`fail/unknown` 未被放行
- [ ] 全不可行有 blocked 恢复路径；异常有触发、影响、行动、决策人
- [ ] `change_log` 和 `run_record.tool_version/commands` 是实际记录
- [ ] 未伪造增益、报价、档期、批准或科学效果
