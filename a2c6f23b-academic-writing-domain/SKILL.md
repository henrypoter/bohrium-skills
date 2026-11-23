---
name: academic-writing-domain
description: 覆盖学术写作全部任务：论文/格式/证据写作/结构/章节/回复/翻译/基金/开题/长文档/转化/思维导图，统一以成稿+论断引用+结构完整+三向一致为机检底座
---

# 学术写作领域总课题

## 领域总览与任务分诊

覆盖学术写作全部任务：论文/格式/证据写作/结构/章节/回复/翻译/基金/开题/长文档/转化/思维导图，统一以成稿+论断引用+结构完整+三向一致为机检底座

**先分诊、后执行**：读输入判定属于哪个子任务，再走下方统一核心流程；子任务的专属交付要点见下表右列。

| 子任务 | 触发信号 | 交付要点 |
|-|-|-|
| 学术论文写作 | 成稿 | 成稿优先+引用绑定 |
| 学术格式与模板适配 | 模板/期刊 | 模板约束+声明字段 |
| 文献证据驱动写作 | 证据组织 | 论断挂引用+来源定位 |
| 论文结构与逻辑优化 | 结构改写 | 章节+逻辑链 |
| 结果与讨论章节写作 | 章节 | 数值三向一致 |
| 审稿回复与论文修改 | 回复审稿 | 逐条对应+改动留痕 |
| 学术翻译与双语写作 | 翻译 | 术语一致+原文对照 |
| 基金申请书写作 | 基金 | 立项依据+可行性 |
| 开题报告与研究计划书 | 开题 | 目标+技术路线 |
| 学位论文与长文档写作 | 长文档 | 分章+全局统一 |
| 科研成果转化写作 | 转化 | 技术+商业价值 |
| 思维导图 | 结构化梳理 | 层级+可编辑 |


在给定材料、图表与文献上产出**可进入修改环节的成稿**，不是提纲或素材堆叠。每条事实性论断能指回材料位置与文献条目。不适用：代写全部研究、虚构数据。

## 调用
- 输入：`/input/case.json` + 材料包 + `task.md`
- 输出：`/app/output/result.json` + 成稿（可编辑源 + 渲染 PDF）
- 工具：`scripts/write_tool.py`（`claim_check` / `structure` / `schema`）
- 模板：`templates/manuscript_spec.md`

## 工作流

### 0. 明确章节契约
按 `templates/manuscript_spec.md` 定：必需章节、字数范围、引用格式、声明字段。

### 1. 成稿优先
先产出结构完整的成稿，再核验。不要先写框架再空转。

### 2. 论断-引用回路（正确性的根本）
每条论断挂 `citations`（`ref_id` 必须在 `references` 表内、`location` 定位到页/段）。**数值论断（样本量、百分比、剂量、P 值）必须有引用**，除非标注为常识。
```bash
python3 scripts/write_tool.py claim_check result.json
```
抓：论断无引用、悬空引用（ref 不在表内）、数值论断无引用、引用缺定位。

### 3. 结构完整性
```bash
python3 scripts/write_tool.py structure result.json
```
必需章节缺一不可、无空章节。

### 4. 三向一致（材料-图表-正文）
数值、单位、样本量、图注在正文与图表间一致；不一致记 critical 并引两处。

### 5. 增益对照
同材料、同章节要求，基础 Agent vs 本 Skill 各跑一次，报：成稿时间、人工返工条目、引用核验命中率。

### 6. 异常处置
| 异常 | 动作 |
|-|-|
| 材料缺图注 | 该图标 unchecked，相关论断降级并注明 |
| 图表与正文冲突 | 记 critical，引正文句与图表句两处 |
| 文献取不到全文 | 依摘要引用并标注，关键论断不依赖未读文献 |
| 材料超长 | 分章处理，声明覆盖范围 |
| 引用格式不认识 | 保留原始格式并标注待人工统一，不臆造字段 |

### 7. 诚实输出
```bash
python3 scripts/write_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{"case_id":"","status":"pass|issues|partial|failed","draft_version":"v1.0",
 "required_sections":["introduction","methods","results","discussion","references"],
 "sections":[{"id":"methods","content":"...","claims":[{"id":"c1","text":"","citations":[{"ref_id":"r1","location":""}]}]}],
 "references":[{"ref_id":"r1","title":"","doi":"","authors":"","year":0}],
 "gain":{"baseline_rework":null,"skill_rework":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 底线
先成稿；论断必有引用且在参考文献表内；数值论断必有引用；章节完整；三向一致。不虚标数值，不缺章节冒充完整。