# result.json 交付与增益契约

```json
{
  "case_id": "与case.json一致",
  "status": "partial|complete|failed",
  "main_output": "/app/output/transformation.md",
  "artifacts": [{"path":"/app/output/transformation_review.md","kind":"md"}],
  "sources": [{"id":"S1","quote":"...","resolved_source":"...","actual_lines":[18]}],
  "changes": [{"segment_id":"p1","action":"revise","before_quote":"...","draft_segment":"...","reason":"...","evidence_ids":["S1"]}],
  "uncertainty": ["材料缺失/无法判断/运行失败分别写"],
  "validation": {"fail":0,"evidence_fail":0},
  "gain": {
    "comparison_status": "pending_platform|completed",
    "protocol": {"same_input":true,"same_constraints":true,"same_permissions":true,"same_budget":true},
    "baseline": null,
    "skill": {"input_sha256":"实际输入哈希","metrics":{"fact_errors":0,"required_missing":0,"manual_edit_items":0,"rework_rounds":1,"evidence_coverage":1}},
    "evidence": []
  }
}
```

同时加入 `case.json.output_contract` 的每个字段；字段无材料可填时保留字段、置 null 并写 uncertainty，不能删字段。`complete` 只允许 evidence/audit fail 都为 0 且无未裁决关键项。pending_platform 不得伪造 baseline；completed 要求两侧输入 SHA-256 相同、非空非负数值 metrics 和可复核 evidence。
