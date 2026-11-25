---
name: feasibility-review
description: 对版本化实验方案做七类可行性审查；机检设备材料四态、样本/预算/排期算术、参数量程交集、十类异常绑定及原文SHA-256定位。
---

# 实验方案可行性评估

## 何时使用 / 边界

读取实际 `/input/case.json`、`/input/task.md` 及随案方案、设备清单、采购/预约、SOP、审批材料，对**每一个输入方案版本**审查：假设与变量、对照组、设备材料、时间成本、参数范围、风险与异常、伦理与安全。适用于组织方声明的 prospective planning scenario；不把示例价格、预约、审批或未来标签当作真实实验室事实。

不代替伦理委员会、安全负责人、设备管理员作批准，不执行实验、不做文献综述或统计分析。未提供的信息写 `not_checked + reason`，绝不默认满足；至少先写一份诚实的 `/app/output/result.json`，再增量补充。无第三方依赖，仅需 Python 3.8+ 标准库。

## 输入、输出与版本

- 输入标识：原样保留 `case_id`；`plan_version` 区分方案版本，不能覆盖历史版本。
- 结果版本：固定 `result_schema_version=feasibility-result-3.0.0` 与 `tool_version=feasibility-exp-tool-3.0.0`。
- 输入指纹：`input_digest`、`permissions_digest` 均为实际输入/权限清单规范化 JSON 的 SHA-256（64 位小写 hex）。
- 输出：`/app/output/result.json`，保留原 `output_contract` 字段，并增加七类 `feasibility.checks`、`exception_register`、`sources`、`gain`。可另写审查表，但不得用正文替代 JSON。
- 每条实质判断的 `evidence[]` 必须有 `source_id / location / quote / sha256`。`sources[]` 登记 `source_id / version / path / sha256`。JSON 定位用 `#/a/b/0`，字符串逐字一致，非字符串用紧凑排序 JSON；文本引用必须是源文本逐字子串。PDF 可登记实际页码定位，并用真实提取文本 `text_path` 验引文；不得从文件名猜内容。

## 执行闭环

```bash
SKILL_DIR=/skills/weekly-skill
R=/app/output/result.json
python3 "$SKILL_DIR/scripts/exp_tool.py" audit "$R"
python3 "$SKILL_DIR/scripts/exp_tool.py" resources "$R"
python3 "$SKILL_DIR/scripts/exp_tool.py" params "$R" --spec /app/work/limits.json
python3 "$SKILL_DIR/scripts/exp_tool.py" verify "$R" --source-root /app/work/source_snapshot
python3 "$SKILL_DIR/scripts/exp_tool.py" schema "$R"
```

所有机检通过才可声明 `status=pass`。有超支、超时、缺样、越界或未决审批时不得放行；有缺材料但审查过程完整可以是 `issues`，有未检查项必须 `partial`，工具未跑通则 `failed/partial` 并记录真实错误。

### 1. 建立可复核的七类检查

每类必须且只有一次：`check_id / category / status / target / conclusion / evidence`。状态为 `pass|fail|conditional|not_checked`；`not_checked` 必须有 `reason`，`conditional` 必须有可执行 `conditions`。`target` 精确到章节、参数或清单行。

1. **假设与变量**：目标是否可证伪；变量写操作定义、类型、单位、范围；缺失不是“满足”。
2. **对照组**：逐组写 `confounder_excluded`，核对能否排除目标混杂。
3. **设备材料**：型号、量程、精度、附件、耗材规格逐项对齐；每项状态只用 `available / outsource / purchase / unavailable`，未知用 `not_checked` 并说明原因。
4. **时间成本**：拆设备占用、人工、等待、检测周转、采购等待和并行组，核对样本来源/数量/保存与预算。
5. **参数范围**：设备、材料、安全多源限制取交集；推荐值、反推上下限、步进、单位与互斥均可重算。
6. **风险与异常**：触发信号、降级/替代动作、止损点与转人工负责人；绑定到检查类别。
7. **伦理与安全**：动物、人体样本、危险试剂、个人数据逐项核对；`pending/not_checked` 必须有动作且不能自行放行。

`feasibility.overall` 只允许 `feasible / conditionally_feasible / infeasible / partial`。“有条件可行”必须把每项条件写成责任人可执行的交付物，例如“M-1 到货并核对 COA 后启动 S2”，不能只写“建议进一步确认”。

### 2. 资源、时间、预算与样本真算

`resources` 命令机检：

- 设备四态和可用设备的型号/精度/附件；材料需求量、库存、采购货期；样本 `required/available/unit/source/storage`。
- 成本逐行 `subtotal=quantity*unit_cost`，`total=Σsubtotal`，并核对 `within_budget`；单位与币种必须显式。
- 单步 `duration=max(equipment_hours,labor_hours)+wait_hours+turnaround_hours`；同一 `parallel_group` 取最长，各组求和；采购步骤前置等待取所有 `purchase` 材料最长 `lead_time_hours`。`elapsed_hours=采购最长等待+Σ并行组关键路径`。
- 样本缺口、预算余额、工期余量从输入重算；算术失败给具体字段定位，不用“大致合理”。

### 3. 参数量程反推

`/app/work/limits.json` 只从实际设备手册、材料规格、安全阈值提取，同名参数可用数组放多条约束：

```json
{"limits":{"temperature":[
  {"min":0,"max":80,"step":10,"unit":"C","source":"设备清单#/limits/temperature"},
  {"min":20,"max":60,"step":10,"unit":"C","source":"材料清单#/thermal_limit"}
]}}
```

对应结果参数写 `name/value/unit/derived_min/derived_max/evidence`。脚本计算 `max(all min)` 与 `min(all max)`，核对推荐值和 `(value-min)%step==0`；缺来源、单位不一致、空交集、互斥和 NaN 均拒绝。它只做确定性算术，不推断未给出的单位换算或安全阈值。

### 4. 异常处置与绑定（逐条必填）

`exception_register` 每条必须有 `code / signal / action / disposition / owner / linked_checks`。`disposition` 只用 `downgrade|label|manual|stop`；`linked_checks` 绑定上述七类之一或多项。

| code / 题面失败情形 | 识别信号 | 具体动作与绑定 |
|-|-|-|
| `plan_missing_pages` 方案缺页 | 页码断档、引用页不存在 | 受影响检查 `not_checked`，索取缺页，降级总体；绑定假设与变量 |
| `missing_parameters` 参数缺失 | 缺 value/unit/min/max | 参数标 `not_checked`，禁止判满足；绑定参数范围 |
| `unknown_equipment` 设备信息不明 | 型号/精度/附件无法对清单 | 设备改 `not_checked`，交设备管理员；绑定设备材料 |
| `ethics_undetermined` 伦理状态未定 | 审批号缺失或 pending | 停止相关步骤，总体降级并列审批材料；绑定伦理与安全 |
| `internal_contradiction` 方案自相矛盾 | 同版本同参数两处冲突 | 列出两处定位，冻结结论，交版本负责人；绑定参数范围 |
| `oversized_document` 超长文档 | 分块清单有未处理页/哈希 | 保留已核验部分，其余标 `not_checked`；绑定假设与变量 |
| `device_failure` 设备故障 | fault、校准过期或不可用 | 改 `unavailable`，核外协；无替代停止；绑定设备材料 |
| `material_batch_variation` 材料批次差异 | 批次/COA 规格改变 | 隔离新批次，重算量程交集，交试剂负责人；绑定设备材料+参数范围 |
| `insufficient_sample` 样本量不足 | `available-required<0` | 判条件不满足，扩样或重审设计；不得擅自减样本；绑定时间成本 |
| `parameter_out_of_range` 参数越界 | 不在交集或不满足步进 | 剔除点；空交集停止并转人工；绑定参数范围+风险与异常 |

### 5. 同输入基础 Agent 对照

平台不提供基线文件时，`gain.status=not_run` 并写原因，质量/效率值为空，**不编分数**。有同权限基线时：

```bash
python3 "$SKILL_DIR/scripts/exp_tool.py" gain /app/work/baseline_result.json "$R" --out /app/output/result_with_gain.json
```

命令强制 `case_id/input_digest/permissions_digest` 相同，否则非零退出。`gain.design` 记录同输入、同权限、同七类口径和重复次数；`quality` 实测七类检查覆盖数、带定位判断数、十类异常覆盖数；`efficiency` 仅在双方 `telemetry` 真有同一计时口径时记录 runtime、返工轮次、补材料轮次，否则 `not_measured`。单次pair记`repetitions=1`，三次重复需分别保存三份真实记录，不能复制成三次。

## 输出骨架（在原有 output_contract 上扩展）

```json
{
  "case_id":"", "status":"partial", "plan_version":"plan-v1",
  "result_schema_version":"feasibility-result-3.0.0", "tool_version":"feasibility-exp-tool-3.0.0",
  "input_digest":"64-hex", "permissions_digest":"64-hex",
  "research_goal":{}, "variables":[], "controls":[], "steps":[], "resources":{}, "parameters":[],
  "risks":[], "judgments":[], "expert_confirmation":[], "unchecked":[],
  "sources":[], "uncertainty":[], "change_log":[],
  "feasibility":{"overall":"partial","conditions":[],"checks":[]},
  "exception_register":[],
  "gain":{"status":"not_run","reason":"","design":{"same_case_id":"","same_input_digest":"","same_permissions":true,"repetitions":1},"quality":{},"efficiency":{}}
}
```

完整**合成最小示例而非正式答案**见 `bench/fixtures/good_result.json`，输入见 `example_input.json`；模板见 `templates/plan_spec.md`，命令细节见 `docs/README.md`。

## 自检与适用限制

```bash
python3 /skills/weekly-skill/bench/bench_run.py
```

bench 对每个命令执行正向零误杀和变异必命中，包括哈希/引文篡改、超支、错排期、样本不足、空交集、步进、NaN、不公平对照。脚本证明确定性检查行为，不证明科学方案天然正确；连续参数、复杂资源日历、非线性能耗、缺失传感器数据需要专家或专用系统复核。离线环境不声称查到了实时库存、价格或审批状态。
