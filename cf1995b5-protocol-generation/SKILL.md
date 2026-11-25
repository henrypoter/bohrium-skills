---
name: protocol-generation
description: 实验方案生成与优化：从研究目标反推假设/变量/对照，按设备量程与预算裁剪参数，核算排期，生成带触发/止损/替代路径的异常预案并保留版本证据
---

# 实验方案生成与优化

把研究目标转成**可排期、可执行、可被同行评审**的方案，而非“准备样品—设置对照—检测分析”的通用目录。适用于有真实科研材料、目标和显式资源合同的生成与迭代。

不适用：替代实验人员承担安全/伦理审批、文献综述、数据统计建模、论文写作；不把规划合同称为真实实验室确认、供应商承诺或实测效应。

## 输入、输出与最小调用

1. 读取真实 `/input/case.json`、`/input/task.md` 和随案材料，记录原 `output_contract`。**所有原字段保留**，本说明新增审计字段；从实际 PDF/JSON 读取，不从标签臆造内容。
2. 工作文件在 `/app/work`，最终 `/app/output/result.json` 与可编辑方案正文；先保存诚实部分产物再迭代。输出含 `case_id/input_id`、主结果、状态、来源定位、不确定性、确认项与变更记录。
3. 纯 Python 3 标准库，无安装依赖。安装后在 `/skills/weekly-skill/`，命令于提交根目录运行或使用脚本绝对路径。
4. 最小合成示例（非官方案例结果）：

```bash
python3 scripts/exp_tool.py check bench/fixtures/good_result.json
python3 scripts/exp_tool.py controls bench/fixtures/good_result.json
python3 scripts/exp_tool.py schema bench/fixtures/good_result.json
python3 bench/bench_run.py
```

## 判对工作流

### 1. 研究目标 → 可检验假设 → 操作化变量

`research_goal.hypothesis` 含比较对象、方向、阈值或范围且可被数据推翻。每个变量必须有 `type/operational_definition/unit/range/measurement_method`，类型为 `independent/dependent/confounder`。自变量如何施加、因变量如何测、混杂如何固定或随机化分别写清；`decision_criteria` 给主要终点、方向、判读阈值和来源定位。

### 2. 从目标和混杂反推对照，不机械套组

先写 `control_requirements[]`：`id/research_goal/confounder/required_control_types/rationale/source_locator`，再让 `controls[].maps_requirement` 回指需求。每个对照说明 `purpose/confounder_excluded/type`。只有空白组并不自动合格；也不是所有研究都必须同时有空白/阳性/阴性，按目标、材料和混杂决定并记录理由。

```bash
python3 scripts/exp_tool.py controls /app/output/result.json
```

该闸检查自变量/因变量存在、需求 ID 唯一、每条需求是否被正确类型对照覆盖、映射是否有效及依据是否可定位。

### 3. 步骤、设备材料与判读绑定

每步写 `id/action/equipment/material/parameter_range/duration/depends_on`，引用资源合同中的真实 ID。设备和试剂写型号、量程、规格、货号（材料有则写），可替代项给验证要求，不可替代项单列。参数写 `name/value/unit/min/max/source/source_locator`，区分设备极限、文献区间、预实验与假设。

### 4. 按设备量程与预算裁剪，不静默改科学设计

从实际输入构造 `constraints-spec.json`。下面是**接口结构示例**；数值只能换成案例实际合同：

```json
{
  "spec_version": "case-contract-v1",
  "budget": {"amount": 2000, "currency": "CNY", "source_locator": "case.json#/budget"},
  "time_window": {"value": 40, "unit": "h", "source_locator": "case.json#/time_window"},
  "equipment": {"reader-open": {"available": true, "booking_status": "open", "source_locator": "case.json#/equipment/reader-open"}},
  "materials": {"reagent-instock": {"available": true, "lead_time": 2, "unit": "h", "source_locator": "case.json#/materials/reagent-instock"}},
  "limits": {
    "temperature": {"min": 4, "max": 40, "unit": "C", "source_locator": "manual.pdf#page=12"},
    "dose": {"min": 0, "max": 80, "unit": "uM", "source_locator": "pilot.json#/dose"}
  },
  "parameter_costs": {"dose": {"fixed_other_cost": 0, "cost_per_unit": 10, "currency": "CNY", "source_locator": "case.json#/dose_cost"}}
}
```

`parameter_costs` 只在案例明确给出线性成本模型时使用：`fixed_other_cost + cost_per_unit × parameter <= budget`。脚本将设备交集与该预算上限求交，输出 `clipped_parameter_domains[].allowed_range/device_max/budget_max/source_locator/cost_source_locator`；没有成本模型时不编造。裁剪建议一律 `requires_confirmation=true`，不把边界截断自动写成科学等效。

成本：`capital + machine + consumables + labor + rework = total`。时间：`preparation + execution + queue + characterization + rework = total`，统一单位并附来源；有并行关系时在正文给关键路径。`sample_size/capacity_per_batch/batches` 必须同时提供，且 `batches >= ceil(sample_size/capacity_per_batch)`。不能只估实验执行而漏准备、机时、表征排队和返工。

```bash
python3 scripts/exp_tool.py optimize /app/output/result.json --spec /app/work/constraints-spec.json
```

该命令核验成本/时间算术、预算和时间窗、样本量与批次、设备可用性和档期、耗材库存与货期、参数可行域；给预算余量、最小批次、裁剪域与处置建议，**不会直接重写结果文件**。

### 5. 风险预案与替代路径

每条风险必须有 `failure_mode/trigger/consequence/mitigation/stop_rule/alternative_path`。至少针对材料能支持的污染、无信号、重复性差、样本不足等模式具体分析，不机械抄列表；触发须可观察，止损点决定是否停，本步失败改什么落在替代路径。安全/伦理和未经确认的替代方案进入 `expert_confirmation`。

### 6. 六要素与证据核验

```bash
python3 scripts/exp_tool.py check /app/output/result.json
python3 scripts/exp_tool.py params /app/output/result.json --spec /app/work/constraints-spec.json
python3 scripts/exp_tool.py schema /app/output/result.json
```

`check` 判假设与变量、对照、设备材料、时间成本、参数范围、风险和异常六类要素，以及变量测量方式、对照映射、风险五件套、判断来源定位和参数自述区间；`params` 再核设备/材料限值。`schema` 查输入/方案/来源/工具版本和实际命令、结构化变更记录。真实异常未解决时不为“变绿”伪改合同，应保存错误清单和 `issues/partial` 产物。

## 异常处置硬表

异常记录到 `exceptions[]`，字段为 `type/trigger/action/alternative_path/impact/decision_owner/status`。`optimize` 对已识别资源阻断同时检查相应记录。缺失、无法判断、运行失败分别说明。

| 题面失败情形 | 识别与处置 | 禁止事项 |
|-|-|-|
| 无设备参数 | `missing_input`；对应资源状态 `unknown`，列设备型号、量程、来源和负责人确认项 | 编造型号/量程或把未知当 pass |
| 无预算/价格 | `missing_input`；成本分项不可核处标 `unknown`，给报价需求与多个资源选项 | 编造价格、擅自降样本量 |
| 时间窗与样本量冲突 | `time_window_conflict`；给超窗 `delta`、最小批次，以及并行/分批/缩样本三选项和科学影响 | 静默丢样本、删对照或压缩必需步骤 |
| 试剂缺货 | `material_unavailable`；给替代试剂、验证对照、货期/成本影响；未解决写 blocked | 未经验证宣称等效替换 |
| 设备排期已满/设备不可得 | `equipment_unavailable`；给替代设备或改期路径，重算量程、成本、排期 | 继续写“可直接执行” |
| 参数窗口为空/越界 | `parameter_window_conflict`；展示设备与预算裁剪域、冲突双方、调整方向 | 只截数值不复核科学等效性 |
| 生成内容不确定 | 区分材料事实、文献依据、预实验和假设；写 `assumptions/uncertainty/confidence`，必要时转专家 | 用肯定语气替代证据 |
| 工具或输入运行失败 | 保留已成功阶段、错误日志和未完成字段；状态 `partial/failed` | 把未运行写成通过 |

## result.json 增量契约

```json
{
  "case_id": "...", "input_id": "...", "status": "pass|issues|partial|failed",
  "plan_version": "plan-v1.0", "schema_version": "result-v3.0", "source_version": "...",
  "research_goal": {"objective": "...", "hypothesis": "...", "constraints": []},
  "decision_criteria": [{"id": "D1", "criterion": "...", "direction": "...", "source_locator": "..."}],
  "variables": [{"id": "V1", "type": "independent|dependent|confounder", "operational_definition": "...", "measurement_method": "...", "unit": "...", "range": "..."}],
  "control_requirements": [{"id": "CR1", "research_goal": "...", "confounder": "...", "required_control_types": ["negative"], "rationale": "...", "source_locator": "..."}],
  "controls": [{"id": "C1", "type": "negative", "purpose": "...", "confounder_excluded": "...", "maps_requirement": "CR1"}],
  "steps": [{"id": "S1", "action": "...", "equipment": "...", "material": "...", "duration": "...", "parameter_range": "...", "depends_on": []}],
  "resources": {"equipment": [], "materials": [], "sample_size": 24, "capacity_per_batch": 12, "batches": 2, "cost_breakdown": {}, "time_breakdown": {}},
  "parameters": [{"name": "dose", "value": 50, "unit": "uM", "min": 0, "max": 100, "source": "...", "source_locator": "..."}],
  "risks": [{"id": "R1", "failure_mode": "...", "trigger": "...", "consequence": "...", "mitigation": "...", "stop_rule": "...", "alternative_path": "..."}],
  "judgments": [{"id": "J1", "claim": "...", "evidence": "...", "source": "...", "source_locator": "...", "confidence": "..."}],
  "assumptions": [], "expert_confirmation": [], "exceptions": [], "unchecked": [],
  "sources": [{"id": "SRC1", "version": "v1", "locator": "manual.pdf#page=12 或 case.json#/budget"}],
  "uncertainty": [],
  "change_log": [{"plan_version": "plan-v1.0", "change": "...", "reason": "..."}],
  "run_record": {"tool_version": "3.0.0", "commands": ["...实际执行命令..."]}
}
```

## 公平增益与完成底线

本地 bench 只验证结构和变异检出，不声称官方分数或真实科学效果。若做基础 Agent 对照，必须同输入、同预算、同来源和工具条件，记录方案成型时间、人工修改条目、返工轮次与原始轨迹；未实测的 `gain` 保持 `null`。

最终判定：目标能被推翻、变量可测、对照从混杂反推、成本时间可重算、参数被量程与预算约束、风险能止损并有替代路径、异常诚实、来源与版本可追溯。
