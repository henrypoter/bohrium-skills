---
name: coverage-gap-analysis
description: 检索覆盖率与遗漏分析：参考集冻结版本、命中判定规则显式、覆盖率与漏检逐条比对、漏检按可操作原因归因到查询/字段/来源、定向补检评估边际收益
---

# 检索覆盖率与遗漏分析

把一个科研问题转成**可复跑、可复核**的检索与筛选闭环：候选集、逐条判定与依据、计数闭合、遗漏归因。适用于系统综述/范围综述/指南证据更新/技术查新的题录筛选环节。

**不适用**：在线数据库全覆盖召回、全局新颖性判定、全文精读与质量评价结论、替代同行评审。本 Skill 处理的是**给定题录的有限快照**，报告里不得声称全局召回率或在线实时覆盖。

## 调用方式

- 输入：`/input/case.json`（case_id + 研究问题 + 题录/材料）、`/input/task.md`
- 输出：`/app/output/result.json` + 工作表 CSV（标注/仲裁/审计/覆盖率）
- 辅助：`scripts/search_tool.py` 的 `dedup / audit / agreement / schema` 四个命令
- 模板：`templates/protocol.md`（协议）、`templates/reason_codes.md`（理由码字典）、`templates/worksheets.md`（三张表列定义）

## 工作流

### 0. 写协议，先于看结果
1. 读 `case.json` 与 `task.md`，把问题拆成对象/机制或方法/人群/时间/比较/证据要求。
2. 按 `templates/protocol.md` 填协议：**每个库的检索式、字段、时间窗、语种、检索日期**逐条写死；纳排标准逐条落到可判定判据并给版本号 v1.0。
3. 标准**先于筛选定稿**；之后任何改动都要升版本，并在 `change_log` 记录改了什么、影响哪些已判记录、是否回溯重判。

### 1. 检索并留痕
每条查询写 `queries[]`：`id/query/database/fields/date_range/run_date`。检索日期缺一不可——没有检索日期就无法复跑。

### 2. 去重（精确 + 近似分开处理）
```
python3 scripts/search_tool.py dedup records.json
```
- 精确键：DOI → arXiv → 标题+首作者+年份。同键自动合并，保留合并依据。
- 近似候选：同年且标题 Jaccard ≥ 0.55 → **只列为候选，不自动合并**，由人工按 DOI/作者/卷期裁决（预印本 vs 正式版）。
- 禁止用"标题肉眼比对"直接给一个剩余条数：必须输出合并组与依据。

### 3. 双人独立标注
- A、B 各自独立按同一版标准逐条判 `include/exclude/maybe`，每条必须带 `reason_code`（取自理由码字典）+ `evidence_snippet`（原文片段）+ `evidence_location`（页码/章节/表号）。
- 双方互不可见结果。先各自出全量，再算一致率：
```
python3 scripts/search_tool.py agreement pairs.json
```
输出决策一致率、Cohen's κ、include 上的理由码一致率。门槛：一致率 ≥ 0.80 且 κ ≥ 0.60；未达标要重训标准或重标，不得直接进下一环节。

### 4. 冲突仲裁
- 分歧分三类：`decision` / `reason_code` / `evidence`。
- 逐条写仲裁结论 + `rationale`（为什么），**不用多数票或平均掩盖实质分歧**；无法裁决的记 `maybe` 并标为待人工复核。

### 5. 计数闭合审计
```
python3 scripts/search_tool.py audit result.json
```
必须闭合：`原始 → 去重后 → 已判定（纳入+排除+待定）`，且 `去重后 ≤ 原始`、`已判定 = 去重后`。不闭合返回非零，**不得交差**。审计日志逐行写步骤/输入数/输出数/操作人/时间/标准版本。

### 6. 覆盖率与遗漏（有参考集时）
逐条比对参考集与命中，未命中按可操作原因归类（M1 同义词未覆盖 / M2 字段过窄 / M3 时间窗截断 / M4 库未收录 / M5 标识异常），`miss_attribution` 必须指到具体查询、字段或来源。补检要记录新增查询式与新增命中，评估边际收益后明确停止条件。

### 7. 增益对照（不要只写自述）
同题录、同标准版本，分别用基础 Agent 与加载本 Skill 各跑一次，报：决策准确率、双人一致率(κ)、人工核对条数。差异要能指到具体记录。

### 8. 异常处置（逐类给动作，不笼统说"注意"）
| 异常 | 处置 |
|-|-|
| DOI 缺失 | 退化为标题+首作者+年份；仍缺则记 `maybe` + E6，不猜 DOI |
| 摘要为空 | 不得据标题硬判；记 `maybe` + E6 并列待取全文 |
| 编码乱码 | 先按 UTF-8/GBK 重解一次；仍乱码则标记字段不可用并记录，不臆造内容 |
| 导出格式不一致 | 按各库字段映射归一（作者/期刊/年/标识符/类型），保留原始响应片段 |
| 标准版本冲突 | 以协议版本号为准，旧版已判记录回溯重判并记 change_log |
| 两位标注者僵持 | 升级仲裁人；仍僵持记 `maybe`，输出"待人工复核"清单，不强行定稿 |
| 库超时/限流 | 记 `unresolved`，在 coverage 里标该库未覆盖，不静默当"无结果" |

### 9. 诚实输出
写 `/app/output/result.json`，再自检：
```
python3 scripts/search_tool.py schema /app/output/result.json
```
`status` ∈ pass/issues/partial/failed。空结果、冲突、权限或接口异常**如实写**，不补造文献；部分完成要写清完成到哪一步、缺什么。

## result.json 契约

```json
{
  "case_id": "...",
  "status": "pass|issues|partial|failed",
  "protocol_version": "v1.0",
  "research_question": {"topic": "", "object": "", "method": "", "time_range": "", "evidence_requirement": "", "scope": ""},
  "queries": [{"id": "Q1", "query": "", "database": "", "fields": "", "date_range": "", "run_date": ""}],
  "records": [{"id": "R1", "title": "", "authors": "", "year": 0, "doi": "", "arxiv": "", "source": "", "language": "", "version": ""}],
  "dedup": {"exact_groups": [], "near_candidates": [], "merged": 0},
  "reason_code_dict": {"I1": "…", "E1": "…"},
  "screening": [{"record_id": "R1", "annotator": "A|B|arbiter", "decision": "include|exclude|maybe", "reason_code": "I1", "evidence_snippet": "", "evidence_location": "", "rule": ""}],
  "agreement": {"decision_agreement": 0.0, "cohen_kappa": 0.0, "n": 0},
  "arbitration": [{"record_id": "", "disagreement_type": "", "decision": "", "rationale": ""}],
  "counts": {"records_raw": 0, "records_dedup": 0, "included": 0, "excluded": 0, "maybe": 0},
  "audit_log": [{"step": "", "input_n": 0, "output_n": 0, "operator": "", "timestamp": "", "rule_version": ""}],
  "coverage": {"reference_total": 0, "retrieved": 0, "missed": 0, "missed_by_code": {}},
  "gain": {"baseline_accuracy": null, "skill_accuracy": null, "kappa_baseline": null, "kappa_skill": null, "manual_checks_saved": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
- 标准先于筛选、版本可回溯；每条判定有理由码 + 真实片段 + 可定位位置；计数闭合；分歧有仲裁理由；未命中能指名到查询/字段/来源。不补造文献，不虚报覆盖率。

## 本课题聚焦
本题聚焦**已知集构建、覆盖率计算、漏检分类与补充检索**。硬要求：①参考集来源写清并**冻结版本**，标注撤稿/无全文等不可用记录；②命中判定规则显式（标识符匹配 / 标题+作者+年近似 / 人工裁决），分子分母都可核对，**严禁用检索结果自身反推分母**；③**未命中不得当「不相关」划掉**，必须逐条留状态；④漏检按 M1 同义词未覆盖 / M2 字段过窄 / M3 时间窗截断 / M4 库未收录 / M5 标识异常 归类，`miss_attribution` 指到具体查询式、字段或来源；⑤补检记录新增查询式与新增命中，评估边际收益后给停止条件，禁止换同义词重跑就宣布遗漏下降。
