---
name: screening-ranking
description: 文献筛选与智能排序：相关性维度先于打分、逐条多维度打分带证据、排序依据可复核、边界条目人工复核、阈值与一致率留痕
---

# 文献筛选与智能排序

把候选文献集按**可复核的相关性**筛选并排序：相关性维度先定义、逐条多维打分带证据、排序依据可解释、边界条目交人工、阈值与一致率留痕。

**不适用**：在线数据库全量召回、用引用数做权威排名、全文精读级质量评价。本 Skill 处理**给定题录的有限快照**，相关性基于题录/摘要可及信息。

## 调用方式

- 输入：`/input/case.json`（case_id + 研究问题 + 候选题录）、`/input/task.md`
- 输出：`/app/output/result.json` + 打分表 / 排序表 / 审计表
- 辅助：`scripts/search_tool.py`（`dedup / audit / agreement / schema`）
- 模板：`templates/protocol.md`、`templates/reason_codes.md`、`templates/worksheets.md`

## 筛选与排序特有原则

| 原则 | 说明 |
|-|-|
| 维度先于打分 | 先定相关性维度（对象/方法/人群/时间/数据类型），再打分；不是凭感觉排 |
| 打分带证据 | 每条每个维度给 0/1/2 分 + `evidence_snippet`（题录/摘要片段），不给"看着相关" |
| 排序依据可解释 | 每条的总分 = 各维度加权和，权重先定；能解释"为什么 A 排在 B 前" |
| 边界交人工 | 阈值 ± 容差内的条目标 `borderline`，交人工复核，不硬切 |
| 一致率留痕 | 双人打分算一致率与 κ，未达标重训维度 |

## 工作流

### 0. 定相关性维度与权重
按研究问题定 3–5 个相关性维度（如：研究对象匹配、方法匹配、人群匹配、时效、数据可得性），每维度给权重（和为 1）与打分锚点（0/1/2 各是什么意思）。写进协议 v1.0。

### 1. 去重
`python3 scripts/search_tool.py dedup records.json` 精确去重 + 近似候选交人工。

### 2. 逐条多维打分
每条记录每维度打 0/1/2 + `evidence_snippet` + `evidence_location`。双人独立打分：
`python3 scripts/search_tool.py agreement pairs.json` 算一致率与 κ（门槛 0.80/0.60），未达标重训维度锚点。

### 3. 加权排序
每条 `total_score = Σ(维度分 × 权重)`，按分降序。排序依据可解释：任意两条能说明分差来自哪个维度。同分按先定的次级键（如年份、被引快照值）。

### 4. 阈值与边界
定纳入阈值；阈值 ± 容差内的标 `borderline` 交人工复核，记录复核结论。**不硬切边界**。

### 5. 计数闭合 + 增益对照
`audit`：`原始 → 去重 → 已打分 → 纳入/边界/排除` 闭合。增益对照：同候选集同维度，基础 Agent vs 本 Skill 报——打分一致率、排序稳定性、人工复核条数、Top-N 重合度。

## result.json 契约

```json
{"case_id":"","status":"pass|issues|partial|failed","protocol_version":"v1.0",
 "dimensions":[{"name":"对象匹配","weight":0.4,"anchors":{"0":"不相关","1":"部分","2":"完全匹配"}}],
 "scores":[{"record_id":"R1","dim_scores":{"对象匹配":2},"total":0.8,
            "evidence":[{"dim":"对象匹配","snippet":"","location":"摘要"}]}],
 "ranking":[{"record_id":"R1","rank":1,"total":0.8,"bucket":"include|borderline|exclude"}],
 "counts":{"records_raw":0,"dedup":0,"scored":0,"include":0,"borderline":0,"exclude":0},
 "gain":{"baseline_topn_overlap":null,"skill_topn_overlap":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 异常处置

| 异常 | 动作 |
|-|-|
| 题录信息不足打分 | 该维度标 `unknown`，不臆造，相关条目降级 |
| 维度间冲突 | 按权重合成，说明取舍，不暗改权重 |
| 双人打分不一致 | 重训锚点后重打，不直接平均 |
| 排序边界模糊 | 标 borderline 交人工，不硬切 |

## 底线
维度先于打分、打分带证据、权重先定、排序可解释、边界交人工、计数闭合。不凭感觉排序，不硬切边界。
