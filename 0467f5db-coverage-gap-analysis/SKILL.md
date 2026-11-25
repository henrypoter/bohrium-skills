---
name: coverage-gap-analysis
description: 检索覆盖率与遗漏分析：冻结独立参考集、逐条命中矩阵、撤稿/标识异常不入假命中、覆盖率复算、漏检归因到查询字段来源、补检真实增量与残余遗漏闭环
---

# 检索覆盖率与遗漏分析

围绕一个已冻结的已知相关参考集完成 **“算覆盖—列漏检—定向补检—复算残余遗漏”**。核心不是检索条数，而是分子分母可独立核对、漏检逐条可定位、补检收益不重复计算。

**适用**：组织方提供的实际来源响应、参考清单、查询与增量状态的有限快照。**不适用**：声称在线实时覆盖、全局召回率/最新性、无源撤稿判断，或把候选结果自身当参考集。不负责全文质量评价和正式系统综述纳排。

## 调用与交付

- 读 `/input/case.json`、`/input/task.md` 与实际材料；原 `output_contract`、`case_id` 和来源标识必须保留。
- 输出 `/app/output/result.json`，附冻结参考集、hit matrix、查询轮次、漏检表和变更记录。
- 标准库工具：`scripts/search_tool.py` 的 `dedup / audit / agreement / schema / covercheck`，版本 `search_tool v3`。Harness 内用绝对路径 `/skills/weekly-skill/scripts/search_tool.py`；开发命令在提交根运行时可用相对路径。
- 模板：`templates/protocol.md`、`templates/reason_codes.md`、`templates/worksheets.md`。
- `bench/fixtures/good_result.json` 仅为调用示意和自测夹具，不是正式案例答案。

## 三条判对硬标准

1. **分母独立且冻结**：`reference_set` 来自综述/指南/专家清单/给定已知集及其实际来源记录，带 `version/frozen_at/source/denominator_rule`。不得从本次候选反推分母，不得删除未命中项让覆盖率上升。
2. **逐条漏检可执行归因**：每条有效参考在 `hit_matrix` 中恰有一次基线和最终状态；每条最终未命中必须有 M1–M5、具体 `query_id/field/source` 组合及实际 `evidence`，不得写成“不相关”。
3. **补检只计真实新增**：每轮保留查询、字段、来源、日期、状态和 `new_hit_ids`；补检后的新增并集必须等于从“基线 miss”转“final hit”的参考 ID。没有新增就不得声称遗漏下降，残漏和未覆盖来源须留下。

## 工作流

### 0. 冻结算法和参考集，先于看覆盖结果
- 写 `protocol_version`、`artifact_version=coverage-result/v3`、`method_version=frozen-reference-incremental-coverage/v3`。
- 每条参考写 `ref_id/title/identifiers/inclusion_reason/countable/retraction_status/identifier_status/fulltext_status`；标识、纳入理由和冻结版本须可回看。
- 预先声明命中规则：`identifier`（规范化 DOI/PMID 等）、`title_author_year`（标题+作者+年近似并留证据）、`manual`（实际裁决理由）；不允许 `looks_similar` 等不可复核口径。
- 预先写 `stop_rule`，例如“连续两轮无新增且每条残漏已有可操作归因则停；来源异常未绝不视为完成”。

### 1. 参考集异常治理，禁止默默改分母
- **撤稿**：`retraction_status=retracted` 必须附 `retraction_evidence/retraction_source`。仅当冻结分母规则预先允许 `exclude_retracted=true` 时 `countable=false`；仍保留记录与 hit matrix 的 `not_applicable_reason`，不可物理删除。
- **撤稿未知**：保留 countable、记未决，status 非 pass；没有来源不得猜撤稿。
- **无全文**：`fulltext_status=unavailable` 只影响可读性，不移出分母，也不等于不相关/漏检。
- **标识冲突**：逐字段写 `identifier_conflicts={field,values,resolution_status,...}`。未解决时不能仅凭 identifier 判命中；有真实题名+作者+年或人工证据才可按相应规则命中，status 非 pass。
- **重复参考**：先运行 `dedup`，精确组与近邻候选分开留痕。分母按冻结裁决后的独立参考数计算，合并没有依据的多篇报道不得随意缩减分母。

### 2. 建基线命中矩阵并独立复算
对每条参考，包括撤稿和无全文项，填：
```json
{"ref_id":"REF1","baseline_hit":true,"final_hit":true,
 "baseline_match_rule":"identifier","baseline_evidence":"DOI 完全匹配",
 "baseline_matched_record_id":"R1","final_match_rule":"identifier",
 "final_evidence":"DOI 完全匹配","final_matched_record_id":"R1"}
```
不命中为显式 `false`，命中必须给 match_rule/evidence/matched_record_id。命中变漏检要写 `status_change_reason`。只以 `countable=true` 的参考作有效分母；零有效分母时率为 null，并报协议/参考集问题，不能报 100%。

保留以下可复算字段：
```text
N = eligible_total
baseline_rate = baseline_retrieved / N
coverage_rate = retrieved / N
missed = N - retrieved
incremental_new_hits = |{基线 miss 且 final hit}|
```
同时保留 `reference_total/eligible_total/excluded_total/baseline_missed`，使撤稿排除也有审计轨迹。

### 3. 漏检归因到具体查询、字段或来源
每条最终漏检在 `miss_attributions` 恰有一行，`coverage.missed_by_code` 由这些行复算：

| 码 | 含义 | 至少需要的定位 |
|-|-|-|
| M1 | 查询未覆盖同义表达 | `query_id` + 能说明缺失词/字段的 evidence |
| M2 | 检索字段过窄 | `query_id + field` + evidence |
| M3 | 时间窗截断 | `query_id` + 实际题录年份/窗口 evidence |
| M4 | 来源库未收录 | `source` + 来源响应/覆盖证据 |
| M5 | 记录标识异常 | `field` + 冲突值/异常响应 evidence |

不得只写“数据库覆盖不足”“关键词不好”。无证据时把归因标为未决假设，而非坐实某原因。

### 4. 定向补检与边际收益
每轮写：
```json
{"round_id":"S1","query":"...","fields":"title/abstract","source":"...",
 "run_date":"ISO-date","status":"ok|empty|timeout|error|permission_denied",
 "target_miss_codes":["M1"],"new_hit_ids":["REF3"],"detail":"...","next_action":"..."}
```
- 正常轮次必须指向目标漏检码，查询由该归因生成；结果的 `discovered_in_round` 回指轮次。
- `new_hit_ids` 只含有效参考中此前未命中、本轮真实新增者。重复命中、基线已命中、失败响应里的“命中”均不计收益。
- 一轮没有新增也是有效结果，须记录 `new_hit_ids=[]`，不得通过更换同义词文字制造“收益”。达到 `stop_rule` 后保留全部未解决项。
- 最终重新运行覆盖计算，列出仍 miss 的参考、原因和查询/字段/来源证据。

### 5. 机检后才交付
```bash
python3 /skills/weekly-skill/scripts/search_tool.py schema /app/output/result.json
python3 /skills/weekly-skill/scripts/search_tool.py audit /app/output/result.json
python3 /skills/weekly-skill/scripts/search_tool.py covercheck /app/output/result.json
```
`covercheck` 独立检查冻结版本、撤稿证据、无全文分母、标识冲突、hit matrix 全覆盖、命中规则/证据、所有分子分母和覆盖率、逐条归因、真实补检增量、来源超时与停止规则。失败返回非零；修复或保留诚实的 `partial/issues`，不得删异常取绿。若案例不要求候选筛选，可按原契约省略仅适用于筛选的 audit 计数，但不能省略 `covercheck`。

有真实同参考集、同预算的基础 Agent 对照时，逐条比较分母、hit status、新增命中和残漏；无对照就填 null，不编造增益或人工复核。

## result.json 新增字段（覆盖原骨架的细化，不替代原字段）

```json
{
 "case_id":"...","status":"pass|issues|partial|failed",
 "artifact_version":"coverage-result/v3","method_version":"frozen-reference-incremental-coverage/v3","protocol_version":"v1.0",
 "reference_set":{"version":"...","frozen_at":"...","source":"...","denominator_rule":{"exclude_retracted":true,"unavailable_fulltext_remains_eligible":true},"records":[]},
 "hit_matrix":[],"search_rounds":[],"miss_attributions":[],"stop_rule":"...",
 "coverage":{"reference_total":0,"eligible_total":0,"excluded_total":0,
   "baseline_retrieved":0,"baseline_missed":0,"baseline_rate":null,
   "retrieved":0,"missed":0,"coverage_rate":null,"incremental_new_hits":0,
   "missed_by_code":{},"complete":false,"unresolved_sources":[]},
 "research_question":{},"queries":[],"records":[],"screening":[],"counts":{},"dedup":{},
 "sources":[],"unchecked":[],"uncertainty":[],"change_log":[]
}
```
`coverage.complete=false` 表示某来源未决，不等于覆盖率一定低；`coverage_rate` 仍按已明确的参考命中矩阵如实复算，并同时披露解释边界。

## 异常处置表

| 题面异常 | 强制识别与处置 |
|-|-|
| 参考集含撤稿 | 有证据才标撤稿；冻结规则允许才 countable=false；矩阵仍保留，禁止直接删分母 |
| 标识冲突 | 列字段与冲突值；未解决不允许 identifier 命中，升级题名作者年/人工裁决并披露 |
| 来源超时 | 该轮 `status=timeout + detail + next_action + new_hit_ids=[]`；来源列入 unresolved_sources、complete=false、总状态非 pass |
| 重复记录 | 精确去重留组合依据，近似多报道交裁决；不能因去重方便扩大或缩小有效分母 |
| 无法获取全文 | fulltext_status=unavailable，仍留分母；不能因此判不相关、撤稿或漏检 |
| 正常空结果 | `status=empty + new_hit_ids=[]` 并继续定向判断；空结果本身不是来源异常 |
| 来源错误/权限不足 | 与 timeout 同样保留未决来源和下一步，不重试撒谎、不靠猜造记录 |
| 零有效分母 | 比率为 null，状态非 pass，要求修复参考集/分母协议 |

## 底线
分母来自独立冻结参考集，逐条状态全保留，撤稿与标识异常有证据，未命中不等于不相关，归因定位到查询/字段/来源，补检只计算真实新增，残余遗漏和超时来源不消失。
