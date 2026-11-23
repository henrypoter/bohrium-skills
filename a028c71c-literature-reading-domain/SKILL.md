---
name: literature-reading-domain
description: 覆盖文献阅读全部任务：问答/图表/多文档/结论提取/证据溯源/公式/复现/数据标准化，统一以支持度分档+证据逐字回链为机检底座
---

# 文献阅读领域总课题

## 领域总览与任务分诊

覆盖文献阅读全部任务：问答/图表/多文档/结论提取/证据溯源/公式/复现/数据标准化，统一以支持度分档+证据逐字回链为机检底座

**先分诊、后执行**：读输入判定属于哪个子任务，再走下方统一核心流程；子任务的专属交付要点见下表右列。

| 子任务 | 触发信号 | 交付要点 |
|-|-|-|
| 科研图表解析 | 读图 | 数值+单位+误差线 |
| 多文档比较与整合 | 跨文档 | 对照+冲突标注 |
| 文献结论与数据提取 | 结构化提取 | 字段+定位 |
| 文献证据溯源与事实核验 | 溯源 | 逐字回链 |
| 公式解析与数学推理 | 公式 | 符号+推导 |
| 论文复现与方法验证 | 复现 | 环境快照+复算 |
| 文献数据清洗与标准化 | 清洗标准化 | 字段+单位统一 |


读完材料后回答问题，每条答案给出**支持度判定**与**逐字证据回链**。材料未报告的内容明确说"没有"，不臆造。不适用：脱离材料的泛化问答、全文翻译。

## 调用
- 输入：`/input/case.json` + 材料 + `task.md`
- 输出：`/app/output/result.json` + 答案正文
- 工具：`scripts/read_tool.py`（`support_check` / `schema`）
- 模板：`templates/support_rubric.md`

## 工作流

### 0. 锁定材料版本
记录 `material_version`（文件/日期/哈希），否则证据无法复核。

### 1. 全文提取（不截断）
PDF 用 `pdftotext`，扫描件说明 OCR 限制。

### 2. 回答 + 支持度分档
每条答案给 `support`：
- `full` 完整支持：原文明确陈述
- `partial` 部分支持：原文支持一部分，其余为推断
- `none` 不支持：原文与此矛盾
- `unknown` 无法判定：材料未报告

**支持度为 full/partial 必须给证据**；`unknown` 要写明"材料未报告 X"。

### 3. 证据逐字回链（可核验的根本）
每条证据 `quote` 必须是**原文逐字片段** + `location`（页/段/表/图）。
```bash
python3 scripts/read_tool.py support_check answers.json --text source.txt
```
抓：引文不在原文（误报）、支持度非法、full/partial 无证据、缺定位。

### 4. 增益对照
同材料、同问题，基础 Agent vs 本 Skill 各跑一次，报：答案支持度准确率、证据可核验率、人工核对条数。

### 5. 异常处置
| 异常 | 动作 |
|-|-|
| 材料未报告 | 判 `unknown`，明确"材料未报告 X"，不用常识补 |
| 证据冲突 | 两处引文并列，标注冲突，不无依据取舍 |
| 扫描件/OCR 差 | 标该段不可读，相关答案降级并注明 |
| 多文档矛盾 | 按文档分别陈述，给出来源 |
| 问题超出材料 | 说明需要的外部信息，不强行回答 |

### 6. 诚实输出
```bash
python3 scripts/read_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{"case_id":"","status":"pass|issues|partial|failed","material_version":"v1",
 "answers":[{"id":"A1","question":"","answer":"","support":"full|partial|none|unknown",
             "evidence":[{"quote":"","location":""}]}],
 "gain":{"baseline_support_accuracy":null,"skill_support_accuracy":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 底线
每条答案有支持度；full/partial 必有逐字证据且回链到原文位置；材料未报告敢说没有；引文可核验。