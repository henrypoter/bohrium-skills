---
name: literature-synthesis-domain
description: 覆盖文献综述全部任务：生成/系统综述/选题创新/趋势分析，统一以论断-引用回路+主题归纳+筛选记录为机检底座
---

# 深度研究与文献综述领域总课题

## 领域总览与任务分诊

覆盖文献综述全部任务：生成/系统综述/选题创新/趋势分析，统一以论断-引用回路+主题归纳+筛选记录为机检底座

**先分诊、后执行**：读输入判定属于哪个子任务，再走下方统一核心流程；子任务的专属交付要点见下表右列。

| 子任务 | 触发信号 | 交付要点 |
|-|-|-|
| 文献综述生成 | 一批文献→综述 | 四步流程+论断引用 |
| 系统性文献综述 | 可复核综述 | 检索式+纳排+计数闭合 |
| 科研选题与创新性评估 | 选题价值 | 问题拆解+创新边界 |
| 研究前沿与趋势分析 | 前沿演化 | 时间序列+演化+空白 |


在一批真实文献上跑完「筛选→主题归纳→证据组织→草稿」四步，交付能进科研讨论的综述。不适用：在线数据库全覆盖、全局召回率、全文精读结论。

## 调用
- 输入：`/input/case.json` + 文献集 + `task.md`
- 输出：`/app/output/result.json` + 综述草稿 + 证据表
- 工具：`scripts/syn_tool.py`（`cite_check` / `theme_check` / `schema`）
- 模板：`templates/evidence_table.md`

## 工作流

### 0. 筛选标准先于写作
按主题写纳排判据（可判定，不含"相关/合理"），记录每条纳入的 `screening_reason`。

### 1. 主题归纳（从文献里长出来）
主题由文献聚成，说明哪些文献聚成哪类；不是套模板。每个主题至少要有 1 条**带引用**的论断支撑。

### 2. 证据组织：论断-引用回路（这是正确性的根本）
每条实质论断必须有 `citations`，且每条引用 `record_id` 在文献清单内、`location` 定位到页/段。**写完立刻核验**：
```bash
python3 scripts/syn_tool.py cite_check result.json
```
抓三类错：`uncited_claims`（论断没引用）、`dangling_citations`（引用的文献不在清单）、引用缺 location。三类清零才可交。

### 3. 覆盖与空白
`theme_check` 看主题覆盖：声明的主题是否都有论断、是否有主题只有论断没有引用。研究空白区分「有排除证据」与「检索遗漏」，并在 uncertainty 说明。

### 4. 增益对照
同文献集、同预算，基础 Agent vs 本 Skill 各跑一次，报：论断引用覆盖率、悬空引用数、人工补引用条数。

### 5. 异常处置
| 异常 | 动作 |
|-|-|
| 缺全文 | 依摘要可判则判并标注"仅摘要"；不可判记 unchecked |
| 元数据不全 | 该字段标 unknown，不臆造 DOI/年/期刊 |
| 文献重复 | 按 DOI/标题+作者+年合并，留依据 |
| 结论冲突 | 正反并列呈现，不做无依据取舍 |
| 超出上下文 | 分段处理并声明覆盖范围 |
| 检索为空 | 区分"确实没有"与"检索式过窄"，放宽重跑对比 |

### 6. 诚实输出
```bash
python3 scripts/syn_tool.py theme_check result.json
python3 scripts/syn_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{"case_id":"","status":"pass|issues|partial|failed",
 "screening_criteria":[{"criterion":"","judgement":""}],
 "records":[{"id":"R1","title":""}],
 "included":[{"id":"R1","title":"","screening_reason":""}],
 "claims":[{"id":"C1","text":"","theme":"","citations":[{"record_id":"R1","location":""}]}],
 "themes":[{"name":"","evidence":[],"gap":""}],
 "counts":{"included":0,"excluded":0,"records_raw":0},
 "gain":{"baseline_cite_coverage":null,"skill_cite_coverage":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 底线
筛选标准先行；论断必有引用且引用在清单内并定位到页/段；主题从文献归纳；空白有据。不补造文献，不虚标覆盖。