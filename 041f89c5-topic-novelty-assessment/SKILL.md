---
name: topic-novelty-assessment
description: 科研选题与创新性评估：把研究问题拆成可检验变量和证伪条件，以最近邻证据判定有界创新，核查可行性前提并给出可回链的综合决策
---

# 科研选题与创新性评估（v2.0.0）

交付四项相互一致的结果：**问题定义、已有工作比较、创新点识别、可行性判断**，并给出综合建议。不是把综述换成“可行/创新”的措辞；不承诺全领域新颖性、数据库完整召回或未做实验的效果。

## 调用与输入契约

- 读取 `/input/case.json`、`task.md`、实际文献与拟议方案/约束；先查看 `environment/resources.yaml`，不得从领域标签补造内容。
- 工作文件放 `/app/work`；最终输出 `/app/output/result.json`，另存比较矩阵、证据表和评估报告。
- 保留 `case.json.output_contract` 的所有原字段；本文件字段为**附加审计字段**，不得替换原契约。
- 工具 `scripts/syn_tool.py` 仅用 Python 标准库，无安装和网络依赖。`bench/fixtures` 仅作合成接口测试，不能复用为正式答案。
- 尽早保存含 `case_id/status/sources/uncertainty/change_log` 的 partial 结果。`status=pass|issues|partial|failed`；检索失败、权限受限或关键前提未知时不得虚标 pass。

## 判对工作流

### 1. 把设想变成可检验问题

`research_question` 至少包含：

- `id/statement/object/expected_outcome`；
- `variables[]`：每个变量有 `name/role/measure`，角色为 independent/dependent/covariate/constraint；
- `comparators[]`：真实可执行的比较基线；
- `falsification_conditions[]`：什么结果会否定设想；
- `success_criteria[]`：预先确定如何评价，而非看完结果再改口径；
- `scope.time_window` 与研究场景。

问题、后续比较维度、创新陈述和实验前提必须共用同一对象与评价口径。

### 2. 留下可复跑的检索覆盖记录

`search_log[]` 每次检索写 `source/query/executed_at/time_window/status`、hits/returned/screened 和 `selected_record_ids`。只使用题目给定文献时，也登记 `source=provided_case_index`、覆盖范围和“未做外部检索”，不能伪装成数据库检索。

`coverage` 填 databases/time_window/languages/limitations/evidence_sufficiency。每个 `origin=search` 的记录必须回链至少一条日志。失败和权限不足也保留日志与 error；检索命中为零只能写“本次未检出”，不能推出“尚无人研究”。纳入不足两篇时状态至少 issues/partial，并标 limited/empty。

纳排判据先于创新判断；每条纳入记录有 `screening_reason`，每条实质 `claims[]` 引用具体 record id、location 和逐字 `quote`。

### 3. 与最近邻逐维划清创新边界

先建 `comparisons[]`，每个真正相近的纳入工作填：

- `record_id`，以及 `dimensions.task/method/data/evaluation/conclusion` 五个可比字段；
- `comparability=comparable|partial|not_comparable`，后两者必须说明不可直接比较原因；
- `citations[]`：引用该工作的具体位置和原文摘录。

每条 `novelty_claims[]` 必须：

- 标 `innovation_type=method|data|scene_transfer|conclusion_correction`；场景迁移不得冒充方法创新；
- `nearest_record_ids` 回链比较矩阵，`differences[]` 逐篇写 existing/proposed/dimension/citations；
- 写 `status=supported|contested|covered|unknown`、`bounded_claim`、最近邻选择及时间窗理由 `recency_rationale`、limitations；
- 固定 `absolute_novelty_claimed=false`，避免“尚无人研究/完全没有先例/no prior work/globally novel”等越界措辞。

### 4. 可行性每个前提有来源或标为假设

`feasibility.premises[]` 必须逐项回应 **data、compute、experiment、time、personnel**；不适用可设 `applicable=false`，但要给理由。适用前提填：

- `status=verified|assumption|unknown`；
- verified 必须有 `evidence[]`：`type=literature|case_input`、精确 location 和 quote；文献证据回链纳入记录，案例约束回链 case.json 路径；
- assumption/unknown 必须写 `assumption_reason` 和可执行的 `validation`；
- 每项都写 `failure_risk/mitigation`。

`decision=feasible|conditional|infeasible|unknown` 与前提一致：仍有假设/未知时不得直接 feasible。结论不能把设想、待验证假设写成已具备条件。

### 5. 冲突、空白与综合结论闭环

- `conflicts[]` 并列至少两篇文献的 `positions`，各带 statement/citations，写 `treatment` 和 `effect_on_decision`；确无冲突时填 `conflict_review.searched=true/note`。
- `research_gaps[]` 回链 comparison 或 novelty claim，标 `bounded_to_search=true`，给 `next_step`，不得把检索局限包装成领域空白。
- `conclusion` 回链 research question、supporting claims 和 novelty claims，并与 feasibility decision 一致；有条件推进必须列 conditions，保留 residual_uncertainties。创新均被覆盖时不能继续无条件推进。

## 版本与来源指纹

`run` 必填 `{case_id,skill_version:"2.0.0",tool_version:"2.0.0",input_sha256,generated_at,source_snapshot}`；时间使用实际 UTC。`sources[]` 对每条记录（含排除项）登记 `{record_id,path,sha256}`，path 相对 `--source-root`，哈希按实际文件字节计算。元数据缺失写 unknown，不能补造。

## 必过机检闸

```bash
python3 scripts/syn_tool.py schema /app/output/result.json
python3 scripts/syn_tool.py question_check /app/output/result.json
python3 scripts/syn_tool.py search_check /app/output/result.json
python3 scripts/syn_tool.py cite_check /app/output/result.json
python3 scripts/syn_tool.py novelty_check /app/output/result.json
python3 scripts/syn_tool.py feasibility_check /app/output/result.json
python3 scripts/syn_tool.py decision_check /app/output/result.json
python3 scripts/syn_tool.py provenance_check /app/output/result.json \
  --input /input/case.json --source-root /input
```

`theme_check` 可辅助检查发现未归类/无证据论断，但不能替代最近邻矩阵。机检只验证结构与一致性；须人工阅读原文，确认真实文献支持比较、创新和结论。

## 异常处置表

| 异常 | 必须动作与输出状态 |
|-|-|
| 检索为空 | 保留检索式、时间窗、零命中和放宽检索日志；coverage=empty，创新标 unknown，不得写“无人研究” |
| 文献过少 | coverage=limited，status 不得 pass；减少创新强度，列出还需哪些最近邻/证据，不用无关文献凑数 |
| 证据互相冲突 | 并列两篇以上立场与定位，分析任务/方法/数据差异，写明对决策影响；无法裁决则 contested/unknown |
| 接口异常 | search_log.status=failed 并记录 error；保留已成功检索，状态降级、uncertainty 记录未覆盖源，不伪造 hits |
| 权限不足 | search_log.status=permission_denied；不绕过控制，只用合法可得材料，明确未覆盖数据库/全文并降级 |
| 缺全文/元数据不全 | 标 abstract_only 或 unknown；不能猜 DOI/年/页码，只作与材料相称的有限判断 |
| 重复文献 | DOI 优先，其次标题+作者+年，保留合并依据，不能重复计入独立证据 |
| 超出上下文 | 分批比较，记录已覆盖 record id，未覆盖进 unchecked，状态至少 partial |

## result.json 附加字段速览

```json
{"case_id":"","status":"partial","research_question":{},"run":{},"screening_criteria":[],
 "records":[],"included":[],"excluded":[],"search_log":[],"coverage":{},"comparisons":[],
 "novelty_claims":[],"feasibility":{},"claims":[],"themes":[],"research_gaps":[],
 "conflicts":[],"conclusion":{},"counts":{},"sources":[],"gain":{},"unchecked":[],
 "uncertainty":[],"change_log":[]}
```

平台若提供基础 Agent 对照，`gain` 可记录同输入同预算的最近邻覆盖率、引用回链率、无依据前提数和人工返工数；未运行填 null，不编造增益。

## 最小合成调用示例（非正式案例结果）

```bash
python3 scripts/syn_tool.py question_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py search_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py novelty_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py feasibility_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py decision_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py provenance_check bench/fixtures/good_result.json \
  --input bench/fixtures/case.json --source-root bench/fixtures/sources
python3 bench/bench_run.py
```

示意输出为各命令 `{"ok": true, ...}`，测试末尾 `total 22/22`。正式案例必须重新生成实际内容、时间与哈希。
