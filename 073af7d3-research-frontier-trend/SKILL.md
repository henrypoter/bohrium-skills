---
name: research-frontier-trend
description: 研究前沿与趋势分析：从文献年度分布提炼可核对的时间趋势，主题演化说清何时因何变化，代表作覆盖各阶段，研究空白有排除证据，每条趋势判断回链文献
---

# 研究前沿与趋势分析

## 用途与边界
从一批文献提炼**可核对**的前沿趋势：时间趋势、主题演化、阶段代表作、研究空白。每条趋势判断必须回链文献与年份。不适用：无时间信息的纯主题综述、凭空预测未来。

## 调用
- 输入：`/input/case.json` + 带年份的文献集 + `task.md`
- 输出：`/app/output/result.json` + 趋势分析正文
- 工具：`scripts/trend_tool.py`（`trend_check` / `schema`）
- 模板：`templates/trend_spec.md`

## 工作流

### 0. 先锁口径
趋势分析最怕「口径漂移」。先写清：时间窗、按什么指标（发文量/主题占比/技术成熟度）、年度分布如何算、文献覆盖范围。`analysis_version` 记录口径版本。

### 1. 年度分布（趋势的地基）
按年份统计文献，给分布表；**趋势判断必须由分布支撑**，不画无依据的"上升/爆发"。拐点说清「在哪一年、因何（标志性工作/技术突破）」。

### 2. 每条趋势论断挂时间 + 引用
每条 `trends[]` 必须有 `year_range`/`period` + `citations`（record_id + 页/段定位）。
```bash
python3 scripts/trend_tool.py trend_check result.json
```
抓：趋势无时间、悬空引用、引用缺定位。三类清零才交。

### 3. 主题演化：分阶段，说清"何时因何变化"
`evolution[]` 每阶段给 `stage` + `period` + 触发事件。不做"早期→发展→成熟"的空套。

### 4. 代表作覆盖各阶段
`representative_works[]` 每篇给 `period` + `record_id` + 为何代表（方法/结论的开创性）。覆盖不到某个阶段要说明。

### 5. 研究空白：有排除证据，不是检索遗漏
`gaps[]` 每条给 `evidence`——用检索式 + 命中数为 0 证明「确实没有」，区分「有排除证据的空白」与「我没查到的遗漏」。

### 6. 增益对照
同文献集、同口径，基础 Agent vs 本 Skill 各跑一次，报：趋势判断可回链率、拐点归因准确率、人工核对条数。

### 7. 异常处置
| 异常 | 动作 |
|-|-|
| 无年份信息 | 无法做时间趋势，标 `unknown`，只做主题归纳并声明 |
| 年度样本过少 | 合并相邻年份或标"低样本"，不强行画趋势 |
| 口径难以对齐 | 并列多个口径分别报告，不无依据取舍 |
| 空白无排除证据 | 降级为"疑似空白"，注明需补检 |
| 趋势与分布矛盾 | 以分布为准，改写趋势论断 |

### 8. 诚实输出
```bash
python3 scripts/trend_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{"case_id":"","status":"pass|issues|partial|failed","analysis_version":"v1",
 "records":[{"id":"R1","title":"","year":2020}],
 "trends":[{"id":"T1","text":"","year_range":"","citations":[{"record_id":"R1","location":""}]}],
 "evolution":[{"stage":"","period":"","trigger":""}],
 "representative_works":[{"period":"","record_id":"","why":""}],
 "gaps":[{"text":"","evidence":""}],
 "gain":{"baseline_traceability":null,"skill_traceability":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 底线
趋势由年度分布支撑、每条判断回链文献与年份、演化有阶段与触发、空白有排除证据。不画无依据的曲线，不把检索遗漏说成研究空白。
