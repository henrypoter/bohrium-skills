---
name: reading-annotation
description: 阅读批注与知识沉淀：批注逐条回到原文页与位置、类型颜色不混、笔记论断有原文支撑、关联有依据不凭关键词、跨版本归并、哈希+脚本版本可复现
---

# 阅读批注与知识沉淀

把散落在 PDF 高亮、页边批注、扫描件手写、网页剪藏里的判断，整理成**可回溯、可检索、可复跑**的知识：批注逐条锚定原文、笔记结构化带证据、关联有依据、入库可检索、过程可复现。

**不适用**：文献检索、文献内容判断、学术写作、目录治理与长期归档制度建设。本 Skill 只做「批注提取—笔记结构化—知识关联—入库检索」这一段。

## 调用方式

- 输入：`/input/case.json` + 含批注的材料（PDF/扫描件/网页/Word）+ `task.md`
- 输出：`/app/output/result.json` + 批注表 / 笔记表 / 关联表 / 检索索引
- 工具：`scripts/annotation_tool.py`（`anchor_check / note_check / link_check / version_check / schema`）
- 模板：`templates/note_schema.md`（笔记结构）、`templates/link_rules.md`（关联判定规则）

## 判对的三件事（本课题的验收核心，不是抽了多少条）

1. **每条批注能回到原文具体页与位置** —— `anchor_check` 逐字核验。
2. **每条笔记论断能指到支撑它的原文片段** —— `note_check` 核验支撑回路。
3. **沉淀条目能被真实问题检索到、被他人按记录复跑** —— 检索索引 + 哈希 + 脚本版本。

## 工作流

### 0. 盘点与可复现底座
列出全部材料文件，对每个文件算 `sha256`、记类型/页数/来源/权限；写 `script_version`。**没有哈希与脚本版本，换台机器结果就不同**——这是可复现的地基。

### 1. 批注提取（保留锚点与类型）
对每条批注记录：`id / type / source_file / page / coords / color / quote(原文逐字) / note(这句为什么重要)`。
- **类型必须区分**：highlight/underline/margin/handwritten/webclip，不混为一类；颜色含义保留。
- 锚点错位是头号问题：扫描件 OCR 坐标漂移、双栏串行读取都要防——每条 `quote` 必须逐字回到原文。
```bash
python3 scripts/annotation_tool.py anchor_check annotations.json --text source.txt
```
抓：类型非法/被混、缺页/位置/引文、引文不在原文（锚点错位）、颜色被抹平。

### 2. 跨版本/重复归并（防版本串味）
同一文献的多个版本、重复下载会把批注拆散。先按 `sha256` 归并：
```bash
python3 scripts/annotation_tool.py version_check files.json
```
内容相同的文件归为一个逻辑文档，批注挂在逻辑文档上；版本不同（哈希不同）的标版本关系，批注不跨版本错挂。

### 3. 笔记结构化（不退化为摘抄）
把批注整理成结构化笔记：`id / kind(question|method|conclusion|reusable|doubt) / claim / support[]`。每条 `claim` 必须有 `support`，每个 support 回指批注或原文片段 + 页/段。
```bash
python3 scripts/annotation_tool.py note_check notes.json
```
抓：论断无支撑、支撑缺定位、类型非法——这正是「笔记退化为摘抄」的反面。

### 4. 知识关联（有依据，不凭关键词）
在批注/笔记/文献/作者/方法间建关联：`{from,to,relation,basis}`。**每条关联必须写明确依据**；只凭"共享一个术语"的关联拒绝。
```bash
python3 scripts/annotation_tool.py link_check links.json
```
抓：关联无依据、依据只是关键词重合（过度连接）。

### 5. 入库与检索入口
产出检索索引：每条沉淀条目可按主题/标签/实体/来源文献/时间检索。说明召回不足与误召回时的处理（如：降低阈值重检、标注低置信条目）。

### 6. 增益对照
同材料同权限，基础 Agent vs 本 Skill 各跑一次，报：批注锚点准确率、笔记可用性（有支撑比例）、关联有效率（有依据比例）、人工修改量。

### 7. 异常处置（逐类，不笼统）
| 异常 | 动作 |
|-|-|
| 加密/损坏文件 | 标 skipped + 原因，不假装读取 |
| 无文本层扫描件 | 说明需 OCR 及置信度，低置信批注标 `unknown`，不臆造锚点 |
| OCR 置信度低 | 该批注标低置信，quote 标待核，不强行锚定 |
| 批注来自旧版本 | 按版本关系挂到对应版本，不错挂到新版 |
| 重复文件 | 按哈希归并，批注不重复计 |
| 权限不足 | 标 skipped + 缺什么权限，不算完成 |
| 材料缺失/无法判断/运行失败 | 三者分开写，不混用，不把未完成写成完成 |

### 8. 诚实输出
```bash
python3 scripts/annotation_tool.py schema /app/output/result.json
```

## result.json 契约

```json
{"case_id":"","status":"pass|issues|partial|failed","script_version":"annotate-v1.0",
 "sources":[{"file":"","sha256":"","type":"","pages":0,"permission":""}],
 "annotations":[{"id":"A1","type":"highlight","source_file":"","page":1,"coords":[],"color":"yellow","quote":"","note":""}],
 "notes":[{"id":"N1","kind":"conclusion","claim":"","support":[{"annotation_id":"A1","quote":"","location":"p1"}]}],
 "links":[{"from":"N1","to":"N2","relation":"supports","basis":"明确依据"}],
 "version_groups":[{"sha256":"","files":[]}],
 "counts":{"files":0,"annotations":0,"notes":0,"links":0,"duplicates_merged":0},
 "skipped":[],"conflicts":[],
 "gain":{"baseline_anchor_accuracy":null,"skill_anchor_accuracy":null},
 "unchecked":[],"uncertainty":[],"change_log":[]}
```

## 底线
批注逐条锚定原文、类型颜色不混、笔记论断有支撑、关联有依据、跨版本按哈希归并、哈希+脚本版本可复现。缺说缺失，失败说失败，不把未完成写成完成。
