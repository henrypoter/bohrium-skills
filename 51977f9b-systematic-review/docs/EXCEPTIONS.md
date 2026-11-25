# 异常处置数据契约 v2.0.0

每个实际异常在 `result.json.exceptions[]` 记录：

```json
{
  "type": "full_text_unavailable",
  "signal": "可复核的输入/接口/判定信号",
  "action": "已执行的降级、标注、重跑或人工转交动作",
  "status": "resolved|degraded|human_review|pending",
  "affected_ids": ["Q1", "R1", "D1", "G1或checkpoint等实际ID"],
  "disposition": "对纳入集、结论和not_checked的影响"
}
```

禁止只写“注意”“谨慎”。`resolved` 要有解决后的 query/decision/read 证据；超时和权限类重试解决另写 `retry_evidence`。`degraded` 说明缩小了什么范围，`human_review/pending` 必须使结果为 issues/partial，不能 pass。

| type（固定枚举） | 识别信号 | 降级/标注/交人工的硬动作 | 禁止 |
|-|-|-|-|
| `empty_search` | query.result_count=0 | 填 `empty_search_handling.classification/actions/follow_up_query_ids`；保留原式、核对字段/同义词/时间，实跑放宽式；gap 仅标有界检索局限 | 将空结果直接写成“该领域无研究”；伪造 result_count |
| `database_or_interface_timeout` | query.error.type=timeout 或接口读取失败 | 写查询 ID 与 checkpoint；预算内同式重试并留 retry_evidence；仍失败则 partial，降级到提供材料并列未覆盖库 | 用旧记忆补命中、无限重试耗尽预算、隐瞒未覆盖库 |
| `full_text_unavailable` | record.availability.full_text=false | 只有摘要足以判定明确设计/人群排除时才 degraded 排除；否则 undecided/not_checked/human_review；禁止全文质量判断 | 以摘要猜测全文数据；把不可得全文当全文纳入 |
| `terminology_ambiguity` | 同义词、缩写、受控词指向不一致 | 在 question elements 记录映射，用 OR 生成新 query 并实跑，旧/新 query IDs 都保留 | 静默默认一种含义；事后删掉未命中的词 |
| `criterion_conflict` | 多条款冲突或 reviewer 票不同 | 按预案 priority；新增裁决 decision，`resolves_disagreement=true` 且 `adjudicates` 链接原票；修标准则升版本重筛 | 覆盖历史票、为单篇文献临时改规则、无理由码 |
| `contradictory_included_evidence` | 纳入原文出现 direct 与 contradicts | `affected_ids` 必须含 conflict ID；矩阵保留两端逐字位置；比较设计/人群/偏倚，未解决则并列并收窄结论 | 用多数票删掉反例、声称一致而无矩阵 |
| `permission_denied` | 文件/接口权限拒绝 | 停止受影响读取、定位 denied 资源和 checkpoint，交人工，结果 partial/failed；不绕过权限 | 伪造读取成功/哈希、尝试越权路径 |
| `duplicate_records` | DOI 或题名作者年规范化冲突 | duplicates 记录 survivor、duplicate IDs、规范化方法与值、字段证据和 DUP 判定 | 仅凭模糊相似合并；误删不同报告 |
| `metadata_missing` | DOI/年/作者等实际缺失 | 字段 unknown，说明影响的去重/定位步骤，必要时人工 | 由题名猜 DOI、年份或期刊 |
| `context_overflow` | 单批超过上下文/预算 | 按 query/record 分批，记录批次范围与输出，合并 decisions 后统一重算；未处理部分 undecided | 声称已读全库、只凭首尾样本综述 |
| `interrupted_run` | 进程/预算中断 | checkpoint 标失败，由最近 completed 恢复；output_path 指向真实部分产物 | 把 pending 当 completed、重跑后删除旧版本记录 |

## 自动检测与人工语义边界

`exception_check` 自动发现：空检索未登记、query timeout 未登记、full_text=false 未登记、pending+pass，以及超时/权限已解决但无 retry evidence。其余类型通过固定字段及与 decisions/conflicts 的回链接受审计；语义上是否真正解决仍需人工复核。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" exception_check /app/output/result.json
python3 "$SKILL_ROOT/scripts/syn_tool.py" audit /app/output/result.json --allow-gain-not-run
```
