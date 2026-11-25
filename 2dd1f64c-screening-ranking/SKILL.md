---
name: screening-ranking
description: 文献筛选与智能排序：全候选逐维带证据评分、缺失信息显式 unknown、可复算加权分与 Top-k、确定性平局、冲突隔离、异常闭环；用于给定题录快照的可复核筛选与排序
---

# 文献筛选与智能排序

把候选文献集按**可复核的相关性**筛选并排序：相关性维度先定义，逐条多维打分带证据，排序依据可解释，边界条目交人工，阈值与版本留痕。

**适用**：`/input/case.json` 给定的有限题录/摘要快照，包括预印本与正式版、缺失字段和若干冲突标注。**不适用**：在线数据库全量召回、全文精读级质量评价、用被引数代替相关性，或声称完成不存在的人工复核。

## 调用与交付

- 输入：`/input/case.json`、`/input/task.md`；先读实际文件和原 `output_contract`，不得按领域标签猜内容。
- 输出：`/app/output/result.json` + 打分表 / 排序表 / 审计表。保留 input 标识、status、来源定位、uncertainty、change_log。
- 工具：`scripts/search_tool.py` 的 `dedup / audit / agreement / schema / rankcheck`，仅 Python 标准库，版本 `search_tool v3`。Harness 内用绝对路径 `/skills/weekly-skill/scripts/search_tool.py`；下列开发命令在提交根运行时可用相对路径。
- 模板：`templates/protocol.md`、`templates/reason_codes.md`、`templates/worksheets.md`。
- 最小示意：`bench/fixtures/good_result.json` 仅是自测夹具，不是正式案例答案。

## 判对原则

| 原则 | 可执行口径 |
|-|-|
| 维度先于打分 | 先定 3–5 维（对象/方法/人群/时间/证据类型）、0/1/2 锚点和权重，权重和为 1；不得看结果后调权重 |
| 打分带证据 | 每条每个已知维度给 0/1/2 + `evidence.snippet/location`；不能只写“相关” |
| 全候选完整处理 | 去重后的每条记录恰好进入一次最终 `scores/ranking/screening`，排除项也不能消失 |
| 缺失不是不匹配 | 摘要/年份缺失写入 `metadata_issues`；未知维度用 `null + unknown_dimensions + unknown_details`，不当作 0 分 |
| 排序可复算 | `total` 由脚本从维度分和先验权重复算；`reason` 说明纳排与先后理由 |
| 同分可稳定复跑 | 固定 `unknown_last → total_desc → record_id_asc`；ID 只定展示先后，不制造科学差异 |
| 边界交人工 | `exclude_max < total < include_min`、全未知或未解决标准冲突均进 `borderline`，不硬切 |
| 一致率诚实 | 有真实双标注才算一致率与 κ；没有第二标注者就如实写 null，不虚构人工或对照 |

## 工作流

### 0. 冻结问题、标准和快照
按研究问题拆对象/方法/人群/时间/证据要求，填写协议 v1.0、纳入阈值、各维度锚点和权重。保存 `snapshot={id,created_at,source,record_count}`。之后标准改动须升版本，记录原因、受影响记录和回溯重判。

### 1. 预检与去重
```bash
python3 /skills/weekly-skill/scripts/search_tool.py dedup records.json
```
精确重复自动成组；近似预印本/正式版只列候选，按作者、DOI、版本关系人工裁决，不自动合并不同研究。逐源写 `source_status`，将“正常零命中”和“接口未覆盖”分开。

### 2. 逐条评分与冲突仲裁
- 每条每维打 0/1/2，保留真实原文片段和可定位位置。信息不足写 unknown 和原因；有相关维度已经 unknown 时，confidence 不得为 high。
- 有 A/B 真实独立标注才运行 `agreement`，一致率 ≥0.80、κ≥0.60 才直接继续；未达标重训锚点或仲裁，不直接平均。
- `criteria_conflicts` 记录 `rule_ids/conflict/status/affected_record_ids`。已解决写 `resolution/resolved_in_version`；未解决写 `next_action`，受影响记录隔离为 `borderline`。

### 3. 缺失感知加权与稳定排序
- 全已知：`total = Σ(dim_score × weight)`。
- 部分未知：固定 `score_formula=known_weight_renormalized`，即 `Σ(已知维度分×已知权重) / Σ(已知权重)`；不得把未知补成 0。
- 全维未知：`total=null`、`bucket=borderline`，排在已知分之后。
- 先冻结 `ranking_policy.version/include_min/exclude_max/k/tie_breakers`，再看结果。固定 `tie_breakers=[unknown_last,total_desc,record_id_asc]`，不得用缺失年份或易变被引数暗破平局。
- `rank` 从 1 连续，`top_k` 等于稳定排序前 k 个 record_id，全部候选仍保留。桶须满足 `total>=include_min → include`，`total<=exclude_max → exclude`，其间或未解决冲突 → `borderline`。
- 同分组每条写 `tie_group/tie_resolution`；大量同分不得隐藏，明确“同组稳定次序不代表科学优先级”。
- 最终 `screening.decision` 与桶一一映射：`include/include、maybe/borderline、exclude/exclude`，且每行 `rule_version=protocol_version`。

### 4. 计数闭合、可核验交付与对照
```bash
python3 /skills/weekly-skill/scripts/search_tool.py schema /app/output/result.json
python3 /skills/weekly-skill/scripts/search_tool.py audit /app/output/result.json
python3 /skills/weekly-skill/scripts/search_tool.py rankcheck /app/output/result.json
```
- `audit` 检查 `原始 → 去重 → 最终判定` 和理由码方向。
- `rankcheck` 独立复算并检查：全候选覆盖、权重/锚点、证据、unknown、阈值和桶映射、rank/Top-k、稳定平局、标准冲突、元数据、接口/权限、快照计数和版本字段。
- 任一命令失败返回非零；修复数据/理由，而不是删异常取绿。不能修复则交付 `partial/issues` 和具体未完成项。
- 增益只使用平台或实际运行保留的同输入、同协议对照；逐条定位 Top-k 和标签差异。没有原生基线记录就填 `null + uncertainty`，不得编造准确率、κ、节省耗时或榜单结果。

## result.json 契约

以下是**字段骨架（非正式案例答案）**。还须保留原 `output_contract` 字段及既有 `dedup/reason_code_dict/agreement/arbitration/audit_log/gain/unchecked`；不得套用骨架时删原字段。
```json
{
 "case_id":"...","status":"pass|issues|partial|failed",
 "artifact_version":"screening-result/v3",
 "method_version":"evidence-weighted-stable-rank/v3",
 "protocol_version":"v1.0",
 "snapshot":{"id":"...","created_at":"ISO-8601","source":"...","record_count":1},
 "research_question":{},"queries":[],"records":[{"id":"R1","title":"...","year":2020,"abstract":"...","source":"..."}],
 "dimensions":[{"id":"D1","name":"对象匹配","weight":1.0,"anchors":{"0":"不符","1":"间接","2":"直接"}}],
 "ranking_policy":{"version":"rank-policy-v1","score_formula":"known_weight_renormalized","include_min":1.5,"exclude_max":0.75,"k":1,"tie_breakers":["unknown_last","total_desc","record_id_asc"]},
 "scores":[{"record_id":"R1","dim_scores":{"D1":2},"unknown_dimensions":[],"unknown_details":{},"total":2.0,"confidence":"high","evidence":[{"dim":"D1","snippet":"原文片段","location":"abstract sentence 2"}]}],
 "ranking":[{"record_id":"R1","rank":1,"total":2.0,"bucket":"include","reason":"对象直接匹配"}],"top_k":["R1"],
 "screening":[{"record_id":"R1","decision":"include","reason_code":"I1","evidence_snippet":"...","evidence_location":"...","rule_version":"v1.0"}],
 "metadata_issues":[],"criteria_conflicts":[],"source_status":[{"source":"...","status":"ok"}],
 "counts":{"records_raw":1,"records_dedup":1,"included":1,"excluded":0,"maybe":0},
 "coverage":{},"sources":[],"uncertainty":[],"change_log":[]
}
```
空候选时 `records/scores/ranking/top_k/screening` 为空、状态非 `pass`，并加 `empty_result={reason,queries_examined,completed_parts,not_completed,next_action}`。这表示流程诚实终止，不表示“世界上无相关文献”。

## 异常处置表

| 题面异常 | 识别字段与强制动作 |
|-|-|
| 候选集为空 | 写 `empty_result` 四项过程信息和 `queries_examined`，状态非 pass；不返回空成功排序 |
| 摘要缺失 | `records[].abstract=null` + `metadata_issues.fields=[abstract]` + action；能据其他真实文本评分则保留，否则相关维度 unknown/待定 |
| 年份缺失 | `year=null` + 同上声明；不填 0/当前年，不用年份破平局 |
| 标注标准互相冲突 | 进入 `criteria_conflicts`；未解决项 borderline + 仲裁下一步，已解决须版本及回溯记录 |
| 大量同分 | 保留同分组，逐条 tie_resolution；按固定键复跑稳定，并明确组内无科学优劣 |
| 接口异常 | `source_status.status=error|timeout`，写 detail/next_action，状态非 pass；该源未完而非零结果 |
| 权限不足 | `permission_denied + detail/next_action`，状态非 pass；不绕过权限、不猜全文内容 |
| 预印本/正式版或多报道 | 精确与近邻去重分开；未裁决组不重复计入独立证据 |
| 第二标注者缺失 | κ 和一致率填 null 并披露；允许有边界的单人初筛，不伪造人工一致性 |

## 底线
维度先于打分、全候选带证据、未知不补造、权重复算、k 值明确、平局稳定、冲突隔离、计数闭合、异常不静默。不凭标题词面或感觉排序。
