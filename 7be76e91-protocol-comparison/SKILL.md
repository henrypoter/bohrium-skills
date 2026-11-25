---
name: protocol-comparison
description: 实验方案比较与选择：固定同口径矩阵，核算全成本与全周期，核验设备/档期/预算/参数硬约束，给有证据的选型、逐方案舍弃理由、敏感性和全不可行恢复路径
---

# 实验方案比较与选择

把固定材料中的多个候选方案放到**同一张可复核矩阵**上，区分“理论可行”“当前资源可行”“被选择”，而不是分别写三份通用流程。适用于给定研究目标、候选方案、有限参数域、设备/耗材/价格/档期合同的比较与选择。

不适用：代替安全/伦理审批、捏造真实实验室或供应商状态、单篇文献综述、实验数据统计建模或论文写作。输入里的规划合同只代表该场景，不能称为真实采购报价、实际排期或实测效果。

## 输入、输出与调用边界

1. 读取真实 `/input/case.json`、`/input/task.md` 和随案材料，先记录原 `output_contract`。**原契约字段原样保留**，下列字段是增量审计字段，不替换原字段；从实际文件取内容，不从文件名猜答案。
2. 在 `/app/work` 工作，尽早写 `/app/output/result.json` 与方案正文；最终保留 `case_id/input_id`、状态、来源定位、不确定性、确认项和变更记录。
3. 工具仅依赖 Python 3 标准库，安装后位于 `/skills/weekly-skill/`。以下命令在提交根目录执行；评测时可将 `scripts/...` 换成绝对路径。
4. `bench/fixtures/good_result.json` 是合成接口示例，不是正式案例答案。工具只能核验结构、算术和显式合同，不能证明科学效应一定成立。

## 判对工作流

### 1. 先锁定口径，再填所有候选

- 保留案例给定的全部候选及各自 `id/plan_version`；通常是 3 个版本化候选，不得只描述自己偏好的一个。
- `comparison_basis.fields` 固定为：`hypothesis / variables / controls / steps / parameters / resources / decision_criteria / risks / evidence / cost_breakdown / time_breakdown / hard_constraints`。每个候选逐项填写，未知写 `unknown`，不得换个方案就换字段。
- 候选内部仍须做到：假设可推翻；变量有操作定义、测量方式、单位、范围；对照说明排除的混杂；步骤绑定设备/材料、先后与并行关系；参数有单位、有限定义域和来源；判读标准含阈值与方向。
- 专家确认项单列。未经确认的安全、伦理、设备可用性或效果推断，不写成已获批准事实。

### 2. 全成本、全周期必须可重算

成本统一币种且分项为 `capital + machine + consumables + labor + rework = total`，其中一次性投入与按次消耗不能混写。时间统一单位且分项为 `preparation + execution + queue + characterization + rework = total`；样品准备、设备排期、表征排队、返工不可省略。若并行，须在正文说明总时长的关键路径；不能只把并行步骤机械相加，也不能漏项后伪称并行。

每个分项表给 `unit/source_locator`。报价、货期、排期未知时是 `missing_input`，不补造数字；不同币种或时间单位未经明确换算依据不得直接比较。

### 3. 硬约束先行，评分不得“抵消不可行”

从案例材料构造 `feasibility-spec.json`（文件名自定），只登记材料实际提供的合同：

```json
{
  "spec_version": "case-contract-v1",
  "budget": {"amount": 1500, "currency": "CNY", "source_locator": "case.json#/budget"},
  "time_window": {"value": 40, "unit": "h", "source_locator": "case.json#/time_window"},
  "equipment": {"reader": {"available": true, "booking_status": "open", "source_locator": "case.json#/equipment/reader"}},
  "materials": {"reagent": {"available": true, "lead_time": 2, "unit": "h", "source_locator": "case.json#/materials/reagent"}},
  "limits": {"temperature": {"min": 4, "max": 40, "unit": "C", "source_locator": "manual.pdf#page=12"}}
}
```

候选 `resource_requirements.equipment/materials` 引用合同 ID；`hard_constraints[]` 逐项写 `id/type/status/source_locator`，`status` 只能是 `pass/fail/unknown`。任一 `fail/unknown` 均不可选，低成本或高主观分不能抵消。

### 4. 选型、舍弃和敏感性缺一不可

- `selection.selected_candidate_id` 只能指向所有硬约束均为 `pass` 的候选。
- `selection.rejected` 对每个未选候选恰好一条具体理由，写清成本、周期、证据或哪条硬约束导致舍弃，不写“综合较差”。
- `selection.rationale/evidence` 把最终结论挂到登记来源；文献、设备手册、预实验、报价和日志不能用笼统“经验”代替。
- `selection.sensitivity[]` 写 `assumption/threshold/effect/evidence`，说明哪个假设或成本/时间变化会翻转结论；翻转后仍须重验硬约束。

### 5. 风险不是“注意安全”

每条风险有 `trigger/consequence/mitigation/stop_rule/alternative_path`，触发条件可观察、后果可判读，替代路径写参数/成本/周期影响和确认人。可接受风险与硬不可行必须分开。

## 异常处置硬表

异常写入 `exceptions[]`，每条包含 `type/trigger/action/impact/decision_owner/status`。未解决时状态诚实标 `issues` 或 `partial`，不得写执行完成。

| 题面失败情形 | 识别与动作 | 放行规则 |
|-|-|-|
| 设备不可得 / 排期满 | `equipment_unavailable`；定位设备合同；给已核验替代设备或改期路径，重算参数、成本、周期 | 替代项仍 `unknown` 就不可选 |
| 耗材缺货 / 货期超窗 | `material_unavailable` 或 `time_window_conflict`；给替代耗材验证要求及成本/货期影响 | 不用未经验证替换冒充等效 |
| 耗材/总成本超预算 | `budget_exceeded`；给超支 `delta`，列可裁剪项及其证据/判读影响 | 不静默删对照、样本或返工预算 |
| 参数窗口冲突 | `parameter_window_conflict`；展示候选区间、设备限值与交集；空交集则换路线 | 不把越界值截到边界就宣称科学等效 |
| 时间窗冲突 | `time_window_conflict`；给并行、分批、延期选项及影响 | 未确认前不压缩关键步骤 |
| 输入缺失 | `missing_input`；该字段 `unknown`，列需确认的合同和来源 | `unknown != pass`，不得推测价格/档期 |
| **候选全部不可行** | `all_candidates_infeasible`；`selected_candidate_id=null`，逐候选给失败理由；`recovery.status=blocked`，写放宽项、替代路径、影响、`decision_owner` | 禁止强行选“相对最好”；补证据后重跑全矩阵 |
| 内容或效果不确定 | `uncertain_content`；区分材料事实、假设、经验推断，给 `uncertainty/confidence` | 不把语言自信当证据强度 |

## 机检顺序（新硬闸）

```bash
# 契约：输入/方案/来源/工具版本、来源定位、运行命令与变更记录
python3 scripts/exp_tool.py schema /app/output/result.json
# 矩阵：同口径字段、算术、可行候选、选择/舍弃、敏感性、全不可行恢复
python3 scripts/exp_tool.py compare /app/output/result.json
# 资源：设备/档期、耗材/货期、预算、时间窗、参数交集
python3 scripts/exp_tool.py feasibility /app/output/result.json --spec /app/work/feasibility-spec.json
```

三条命令均须 `ok=true`；若真实异常使 `feasibility` 返回非零，保留违规清单与诚实 `issues/partial` 产物，不为“变绿”改假数据。已有 `check` 与 `params --spec` 可用于选定方案正文的六要素和单参数复核。所有实际执行命令写入 `run_record.commands`，工具版本写 `run_record.tool_version`。

## result.json 增量契约（字段结构）

```json
{
  "case_id": "...", "input_id": "...", "status": "pass|issues|partial|failed",
  "plan_version": "comparison-v1.0", "comparison_schema_version": "matrix-v3.0", "source_version": "...",
  "comparison_basis": {"cost_currency": "CNY", "time_unit": "h", "hard_constraint_rule": "任一非pass不可选", "fields": ["...统一字段..."]},
  "candidates": [{"id": "P-A", "plan_version": "A-v1.2", "hypothesis": "...", "variables": [], "controls": [], "steps": [], "parameters": [], "resources": {}, "resource_requirements": {"equipment": [], "materials": []}, "decision_criteria": [], "risks": [], "evidence": [], "cost_breakdown": {}, "time_breakdown": {}, "hard_constraints": []}],
  "selection": {"selected_candidate_id": "P-A", "rationale": "...", "evidence": [], "rejected": [{"candidate_id": "P-B", "reason": "..."}], "sensitivity": [{"assumption": "...", "threshold": "...", "effect": "...", "evidence": "..."}]},
  "exceptions": [], "recovery": {"status": "not_blocked|blocked", "action": "...", "decision_owner": "..."},
  "sources": [{"id": "SRC1", "version": "v1", "locator": "manual.pdf#page=12 或 case.json#/equipment/reader"}],
  "uncertainty": [], "expert_confirmation": [], "unchecked": [],
  "change_log": [{"plan_version": "comparison-v1.0", "change": "...", "reason": "..."}],
  "run_record": {"tool_version": "3.0.0", "commands": ["...实际执行命令..."]}
}
```

最小可运行示例：

```bash
python3 scripts/exp_tool.py schema bench/fixtures/good_result.json
python3 scripts/exp_tool.py compare bench/fixtures/good_result.json
python3 bench/bench_run.py
```

## 公平增益与完成底线

本地 `bench` 只证明命令及变异检出，不声称官方得分、科学有效性或相对榜首提升。若另做基础 Agent 对照，必须同输入、同预算、同工具可用性，记录候选字段对齐耗时、人工修改项、返工轮次及原始轨迹；平台未提供的数字保持 `null`。

交付前：所有候选同表、算术可重算、选择未越硬约束、舍弃具体、敏感性可翻转、全不可行不硬选、来源可定位、版本可追踪。
