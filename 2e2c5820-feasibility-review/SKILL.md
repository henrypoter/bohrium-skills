---
name: feasibility-review
description: 实验方案可行性评估：六要素齐备、参数逐项核对设备量程、风险带触发与止损、方案可版本化复核
---

# 实验方案可行性评估

把研究目标转成**能排期、能执行、能被同行评审**的方案：假设可检验、变量可测、对照能排除混杂、参数在设备允许范围内、风险有预案。

不适用：替代实验人员承担安全与伦理审查、替代统计分析、代写论文。

## 调用

- 输入：`/input/case.json`、`/input/task.md`、设备/材料清单与约束
- 输出：`/app/output/result.json` + 方案正文
- 工具：`scripts/exp_tool.py`（`check` / `params` / `schema`）
- 模板：`templates/plan_spec.md`（六要素检查表 + 参数表 + 风险矩阵）

## 工作流

### 0. 目标 → 可检验假设
写 `research_goal.hypothesis`：**可被数据推翻**的陈述（含方向、比较对象、阈或范围）。"研究 X 的机制"不是假设；"X 在 A 条件下使 Y 上升 ≥20%"才是。

### 1. 变量：给操作定义，不给名词
每个变量必须有 `operational_definition`（怎么测）、`unit`、`range`，并标 `type`（independent/dependent/confounder）。混杂因素要单独列出，不要藏在自变量里。

### 2. 对照：说明排除哪类混杂
每个对照写 `confounder_excluded`。没有"排除什么"的对照等于没设对照。

### 3. 步骤 / 设备 / 材料 / 时间
步骤绑定设备型号与耗材规格；写清 `time_estimate`（可分步时长与并行关系）与成本估算。**可替代与不可替代项要标出来**（试剂缺货时的替代路径）。

### 4. 参数：逐项核对量程，不只看"看起来合理"
写 `parameters`：`name / value / unit / min / max`。然后用设备与材料限值核验：
```bash
python3 scripts/exp_tool.py params result.json --spec limits.json
```
`limits.json` 里放设备手册/材料耐温/安全阈值。脚本会抓三类问题：**超出上限、单位不一致、spec 未声明限值（须补来源）**。参数依据注明来自设备手册/预实验/文献。

### 5. 风险与异常：三件套缺一不可
每个风险必须有 `trigger`（什么信号触发）、`mitigation`（怎么救）、`stop_rule`（何时止损）。只写"注意安全"不算。

### 6. 六要素自检
```bash
python3 scripts/exp_tool.py check result.json
```
输出 `missing_elements` 与逐项错误（假设缺失、变量缺操作定义/单位、对照未说明混杂、风险三件套缺项、判断缺证据来源、参数越自述区间）。全部清零再接下一步。

### 7. 增益对照
同目标、同资源约束，基础 Agent vs 本 Skill 各跑一次，报：六要素完整度、需人工修改条目数、评审返工轮次。

### 8. 异常处置
| 异常 | 动作 |
|-|-|
| 无设备参数/预算 | 该要素标 `unknown` 并给出"需确认清单"，**不编造型号与价格** |
| 约束冲突（时间窗 vs 样本量） | 列出冲突双方与取舍空间，给两个可行方案供选择，不悄悄牺牲一方 |
| 依赖不可用（试剂缺货/设备排期满） | 给替代路径与预计影响，标为 `blocked` 而非"已完成" |
| 参数无可行解 | 说明冲突的参数对与放宽方向，转人工决策 |
| 生成内容不确定 | 写明哪些是文献依据、哪些是经验推断，标 `confidence` |
| 安全/伦理未明确 | 单列进 `expert_confirmation`，不自行放行 |

### 9. 诚实输出
```bash
python3 scripts/exp_tool.py schema /app/output/result.json
```

## result.json 契约

```json
{
  "case_id": "", "status": "pass|issues|partial|failed", "plan_version": "plan-v1.0",
  "research_goal": {"objective": "", "hypothesis": "", "constraints": []},
  "variables": [{"id": "V1", "name": "", "type": "independent|dependent|confounder",
                 "operational_definition": "", "unit": "", "range": ""}],
  "controls": [{"id": "C1", "type": "blank|positive|negative|gradient", "purpose": "",
                "confounder_excluded": ""}],
  "steps": [{"id": "S1", "action": "", "equipment": "", "material": "", "duration": "", "parameter_range": ""}],
  "resources": {"equipment": [], "materials": [], "sample": "", "time_estimate": "", "cost_estimate": ""},
  "parameters": [{"name": "temperature", "value": 75, "unit": "C", "min": 20, "max": 90, "source": "设备手册 p12"}],
  "risks": [{"id": "R1", "failure_mode": "", "trigger": "", "consequence": "", "mitigation": "", "stop_rule": ""}],
  "judgments": [{"id": "J1", "claim": "", "evidence": "", "source": "", "confidence": ""}],
  "expert_confirmation": [],
  "gain": {"baseline_completeness": null, "skill_completeness": null, "rework_rounds_saved": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
假设可检验、对照说明排除什么、参数不越量程、风险有止损点、需专家确认的单列。缺设备/预算就写 unknown，不编造。

## 本课题聚焦
本题聚焦**可行性与资源核验**：设备型号/精度/附件与现有条件比对（已具备/可外协/需采购/不具备四态）、耗材货期、样本量与来源、伦理审批级别与时长。审查意见要落到方案的具体章节与清单行，「有条件可行」必须写清是哪些条件。
