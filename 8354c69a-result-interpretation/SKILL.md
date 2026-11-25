---
name: result-interpretation
description: 实验结果解释与异常分析：五段结论(趋势/异常点/原因/复核/后续实验)、异常点绑定批次通道维度、原因按可检验性排序、每条结论回指数据文件与字段、可复算
---

# 实验结果解释与异常分析

把一份实验数据解释成**五段可检查的结论**：结果趋势、异常点、可能原因、复核步骤、后续实验建议。每条结论都要回指到具体数据文件、字段、阈值与版本，让人能照着复算。

**不适用**：实验方案设计、统计分析软件替代、新发现的事实认定。本 Skill 产出的是「可复核的解释性结论」，判定依据透明，不替代研究者的最终科学判断。

## 判对（本题评分核心，不看写了多少结论）

1. 五段结论是否齐备且可检查（趋势/异常/原因/复核/后续）。
2. 趋势方向、拐点、幅度是否与原始读数一致；异常点是否落在真正异常的对象上；原因是否有数据支持。
3. 是否覆盖全部指标、对照、重复与边界，并交代未解释部分。
4. 每条结论能否回指具体数据文件、字段、阈值与版本，他人能否复算。

## 调用
- 输入：`/input/case.json`、`/input/task.md`、数据文件（CSV/TXT/表）
- 输出：`/app/output/result.json`
- 工具：`scripts/interp_tool.py`（`interp_check` / `schema`）

## 工作流（五个方向逐一过）

### 0. 锁定数据版本
记录 `analysis_version` + `data_sources`（每个数据文件 + 字段 + 阈值），否则结论无法复算。

### 1. 结果趋势（方向1）
从读数给走势、拐点、平台期、偏离幅度，每条写明所依据的**区间、对照、拟合方式**。方向/拐点/幅度必须与原始读数一致，不凭空画趋势。

### 2. 异常点（方向2）
在样本、批次、通道、孔位、时间点等维度上定位异常，每条给：`dimension`（绑定到哪个维度）、`severity`、`threshold`（判定阈值）、`deviation`（与对照或重复的偏离关系）。**异常必须落在真正异常的对象上**，不是"某批数据偏高"这种悬空判断。

### 3. 可能原因（方向3）
按**证据强度/可检验性降序**给原因候选，每条带：
- `evidence_support` 支撑证据
- `evidence_exclude` 排除证据（能排除什么）
- `correlation_risk` 把相关误当因果的风险
原因排序必须可解释，不是"都可能是原因"。

### 4. 复核步骤（方向4）
把结论拆成第二个人能执行的核查动作：回查具体数据文件与字段、核对批次与设备日志、加做对照或平行重复。每条有 `action` + `target`。

### 5. 后续实验建议（方向5）
依据原因候选与证据缺口给下一轮实验改动：补对照、加密采样点、调整参数范围、扩大重复数。每条有 `rationale`。

### 6. 增益对照
同数据同权限，基础 Agent vs 本 Skill 各跑一次，报：趋势判读一致率、异常定位命中率、人工返工条目数。

### 7. 异常处置
| 异常 | 动作 |
|-|-|
| 数据缺失 | 标 `unexplained` 或 `unknown`，不臆造读数 |
| 重复数不足 | 标低置信，注明"重复不足以支撑"，不强行下结论 |
| 对照缺失 | 结论降级并注明"无对照，偏离判断不可靠" |
| 读数超量程/饱和 | 该点标 `saturated`，不当作真实异常 |
| 结论互相冲突 | 并列呈现，标 `uncertainty`，不无依据取舍 |
| 数据需申请 | 标 `blocked` + 申请途径 |

### 8. 诚实输出
```bash
python3 scripts/interp_tool.py interp_check /app/output/result.json
python3 scripts/interp_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{
  "case_id": "", "status": "pass|issues|partial|failed",
  "analysis_version": "v1 / 2026-11-25",
  "data_sources": [{"file": "", "field": "", "threshold": "", "version": ""}],
  "trends": [{"direction": "", "interval": "", "control": "", "fitting": "", "knee": "", "deviation": ""}],
  "anomalies": [{"dimension": "batch", "severity": "", "threshold": "", "deviation": "", "evidence": ""}],
  "causes": [{"candidate": "", "evidence_support": "", "evidence_exclude": "", "correlation_risk": "", "testability": 3}],
  "recheck_steps": [{"action": "", "target": ""}],
  "next_experiments": [{"change": "", "rationale": ""}],
  "unexplained": [], "gain": {"baseline": null, "skill": null},
  "unchecked": [], "uncertainty": [], "change_log": []
}
```

## 底线
趋势回读数、异常落对象、原因有证据且按可检验性排序、复核可执行、每条结论可复算。不把未解释的说成已解释。
