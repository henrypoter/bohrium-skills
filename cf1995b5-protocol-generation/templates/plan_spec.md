# 方案生成规格表（生成题）

> 合成模板不是正式答案。输入缺失标 `unknown`，安全/伦理/设备可用性未确认不得写成已批准。

## 1. 六要素与判读

| 要素 | 必填内容 |
|-|-|
| 假设与变量 | 可推翻假设；变量 type/操作定义/测量方式/单位/范围；自变量、因变量、混杂分列 |
| 对照组 | 目标→混杂→所需类型→实际 controls 映射；每组说明排除什么 |
| 设备材料 | 实际合同 ID、型号/量程/规格/货号（有则填）、替代项验证 |
| 时间成本 | 分步与依赖、准备/执行/排队/表征/返工；机时/耗材/人力/一次性/返工 |
| 参数范围 | value/unit/min/max、设备或文献或预实验来源与定位 |
| 风险异常 | 触发/后果/缓解/止损/替代路径，安全与专家确认 |
| 判读标准 | 主要终点、方向、阈值、来源定位 |

## 2. 目标反推对照表

| requirement id | research_goal | confounder | required_control_types | rationale/source_locator | 实际 control id/type |
|-|-|-|-|-|-|
| CR1 |  |  |  |  |  |

不机械要求所有对照类型，但每条需求必须被正确类型覆盖，`maps_requirement` 必须有效。

## 3. 参数裁剪与排期

设备可行域：`[max(plan.min, limit.min), min(plan.max, limit.max)]`。
若有显式线性成本模型，再加入预算上限：`(budget-fixed_other_cost)/cost_per_unit`；没有模型不得臆造。裁剪结果只作待确认建议，需复核科学等效性。

- 成本：`capital + machine + consumables + labor + rework = total`。
- 时间：`preparation + execution + queue + characterization + rework = total`；并行另写关键路径。
- 批次：`sample_size/capacity_per_batch/batches` 同时提供，且 `batches >= ceil(sample_size/capacity)`。

## 4. 风险与异常

| type/failure_mode | trigger | consequence/impact | mitigation/action | stop_rule | alternative_path | decision_owner/status |
|-|-|-|-|-|-|-|
| 无信号/污染/重复性差（按材料取舍） |  |  |  |  |  |  |
| missing_input |  |  |  |  |  |  |
| time_window_conflict |  |  |  |  |  |  |
| material_unavailable |  |  |  |  |  |  |
| equipment_unavailable |  |  |  |  |  |  |
| budget_exceeded / parameter_window_conflict |  |  |  |  |  |  |

## 5. 交付闸

```bash
python3 scripts/exp_tool.py check /app/output/result.json
python3 scripts/exp_tool.py controls /app/output/result.json
python3 scripts/exp_tool.py optimize /app/output/result.json --spec /app/work/constraints-spec.json
python3 scripts/exp_tool.py schema /app/output/result.json
```

- [ ] 原 `output_contract` 字段和 `case_id/input_id` 保留
- [ ] 六要素与判读可执行，对照从目标/混杂反推
- [ ] 成本时间算术、样本量批次、设备档期、货期、量程与预算域已核
- [ ] 风险有止损和替代路径；异常有 action/impact/decision_owner
- [ ] 来源含 `id/version/locator`；参数和判断均有定位
- [ ] `change_log` 有版本/变化/原因；`run_record` 记录实际命令
- [ ] 未伪造增益、资源状态、批准或实验效果
