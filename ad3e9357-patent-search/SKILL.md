---
name: patent-search
description: 专利与技术文献检索：专利号规范化与同族归并、IPC/CPC主题检索式、法律状态回官方登记核验、数据源授权绿黄红分级、结论证据强度分级
---

# 专利与技术文献检索

把技术查新 / 可专利性检索做成**可复跑、可复核**的闭环：专利号规范化、同族归并、IPC/CPC 检索式、法律状态核验、逐条判定留痕、计数闭合、遗漏归因。

**不适用**：全球专利库实时全量检索、新颖性/创造性的法律结论、FTO（自由实施）法律意见。本 Skill 处理**给定题录/可及数据源的有限快照**，不得声称覆盖全部专利局数据。

## 调用方式

- 输入：`/input/case.json`（case_id + 技术问题 + 题录/材料）、`/input/task.md`
- 输出：`/app/output/result.json` + 专利清单/同族表/法律状态表/审计表
- 辅助：`scripts/search_tool.py`（`dedup / audit / agreement / schema`）
- 模板：`templates/protocol.md`、`templates/reason_codes.md`、`templates/worksheets.md`

## 专利特有概念（先建立，再检索）

| 概念 | 处理 |
|-|-|
| 专利号规范化 | 统一为 `国别代码+类型+序号`（如 `CN101234567A`），去空格/点号，保留 kind code（A/B/C） |
| 同族（family） | 同一发明在多局的申请归为一族，族内只评一次，记 `family_id` |
| IPC/CPC | 用国际专利分类号定位技术领域，比纯关键词更抗术语差异 |
| 法律状态 | 有效 / 失效 / 审查中 / 驳回 / 届满，须回官方登记（著录项目）核验，不凭摘要推断 |
| 数据源授权 | 官方局（绿）/ 商业库（黄，注意条款）/ 爬虫抓取（红，避免）三级 |

## 工作流

### 0. 技术拆解 → 检索要素
把技术问题拆成：**技术特征（结构/步骤/参数）、应用领域、要解决的技术问题**。据此给出候选 IPC/CPC 分类号（写到小类/大组），再补关键词与同义词。先写检索协议（库、分类号、关键词、时间窗、日期），版本 v1.0。

### 1. 专利号规范化与同族归并
对每条记录：
- 规范专利号（去空格/点、补 kind code），无法规范的标 `maybe` 记原因。
- 按 `family_id` 归并同族；无 family 字段时按"优先权号/申请号"近似归族，**只列候选不自动合并**，由人工裁决。
- `python3 scripts/search_tool.py dedup records.json` 做精确去重；同族归并在去重之后单独成表。

### 2. 分类号 + 关键词组合检索
- 检索式 = `IPC/CPC ∧ (关键词 OR 同义词)`，每个库一条 `queries[]`（库/分类号/关键词/时间窗/检索日期）。
- 官方局优先（CNIPA/USPTO/EPO/WIPO），商业库标注授权级别（绿/黄/红）。

### 3. 法律状态核验（专利特有，不可省）
对纳入的每条专利，回官方登记核验法律状态：`legal_status ∈ {有效, 失效, 审查中, 驳回, 届满, 未知}` + `status_source`（哪个登记、查询日期）。**凭摘要或第三方页面推断的一律标 `未知` 并记 uncertainty**。

### 4. 逐条判定 + 仲裁 + 审计（复用可复核机制）
- 双人独立按协议判 `include/exclude/maybe`，带 `reason_code + evidence_snippet + evidence_location`。
- `agreement` 算一致率与 κ（门槛 0.80/0.60）；冲突逐条仲裁，不用多数票。
- `audit` 计数闭合：`原始 → 去重 → 归族 → 已判定`，不闭合不交差。

### 5. 覆盖率与遗漏
有参考集时逐条比对，未命中按原因归类（同义词/分类号漏选/时间窗/库未收录/号异常），`miss_attribution` 指到具体查询或分类号；补检记新增检索式与边际收益，明确停止条件。

### 6. 结论证据强度分级
每条结论标证据强度：`官方登记`（强）/ `权威数据库`（中）/ `第三方页面`（弱）/ `推断`（须标 uncertainty）。新颖性只说"在本快照内未见相同技术特征"，不说"全球首创"。

### 7. 增益对照
同题录、同协议，基础 Agent vs 本 Skill 各跑一次，报：专利号规范化率、同族归并准确率、法律状态核验覆盖率、人工核对条数。

## result.json 契约

```json
{"case_id":"","status":"pass|issues|partial|failed","protocol_version":"v1.0",
 "records":[{"id":"P1","patent_no":"CN101234567A","family_id":"F1","ipc":"G06F17/30"}],
 "queries":[{"id":"Q1","database":"CNIPA","ipc":"G06F17/30","keywords":"","date_range":"","run_date":""}],
 "included":[{"id":"P1","reason_code":"","evidence_snippet":"","evidence_location":"",
              "legal_status":"有效","status_source":"CNIPA著录 2026-11","confidence":"官方登记"}],
 "counts":{"records_raw":0,"dedup":0,"families":0,"screened":0},
 "gain":{"baseline_legal_coverage":null,"skill_legal_coverage":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 异常处置

| 异常 | 动作 |
|-|-|
| 专利号无法规范化 | 标 `maybe`，记原始串与原因，不臆造 |
| 同族关系不确定 | 只列候选，交人工，不自动归并 |
| 法律状态查不到 | 标 `未知` + status_source 记查询渠道，不凭摘要猜 |
| 官方库访问受限 | 降级到可及库并声明覆盖范围，不声称全局 |
| 分类号拿不准 | 给多个候选 IPC/CPC 并说明取舍依据 |

## 底线
专利号必规范化、同族必归并（候选制）、法律状态必回官方核验、计数必闭合、结论分证据强度。不声称全局覆盖，不做法律定性结论。
