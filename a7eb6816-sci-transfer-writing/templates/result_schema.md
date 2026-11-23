# result.json 输出契约（放 /app/output/result.json）

## 必填字段
- `case_id`：来自 /input/case.json。
- `status`：`complete` | `partial` | `failed`；partial/failed 须在 uncertainty 说明缺了什么。
- `deliverable`：`{path, genre, audience, word_count, meets_constraints}`，path 指向 /app/output 下可编辑成稿。
- `fact_source_map`：数组，每条 `{fact, draft_expression, source_locator, action, reason}`；action ∈ kept|rephrased|compressed|deleted|term_substituted；关键数值、样本量、对比基准、图表编号逐条列出。
- `change_log`：数组，每条 `{location, action, reason}`；覆盖每处删改，原作者可按段复核。
- `term_glossary`：数组，`{term, expansion_or_plain, locked_form}`。
- `open_questions`：需人工确认项（数据冲突、口径不明等）。
- `material_gaps`：材料缺口（无应用数据、无成本、无 TRL 等），对应正文的【材料缺口】标注。
- `sources`：实际读取的文件，`{path, role}`；role ∈ task_spec|source_material。
- `uncertainty`：不确定性与局限，诚实填写；无则空数组。
- `verification`：`{check_report_path, added_numbers, strong_word_escalation, caveats_missing, advice_escalation, causal_escalation, extrapolation_escalation, genre_pass}`，填 check 报告计数；added_numbers 及限定语丢失/三维越级/体裁缺项须为 0 或已逐条处置。
- `budget`：`{model_requests_used, elapsed_seconds}`，诚实填写，不得虚构。

## 最小合法示例（结构示意，非真实案例结果）
```json
{
  "case_id": "example-000",
  "status": "partial",
  "deliverable": {"path": "/app/output/deliverable.md", "genre": "科普文章", "audience": "公众", "word_count": 620, "meets_constraints": true},
  "fact_source_map": [{"fact": "效率 21.3%", "draft_expression": "效率 21.3%", "source_locator": "materials/paper.txt 第3段", "action": "kept", "reason": "核心指标必须保留"}],
  "change_log": [{"location": "第2段", "action": "deleted", "reason": "方法细节超出公众受众需要"}],
  "term_glossary": [{"term": "PCE", "expansion_or_plain": "光电转换效率", "locked_form": "光电转换效率"}],
  "open_questions": [],
  "material_gaps": ["材料未提供成本与产业化验证数据"],
  "sources": [{"path": "/input/task.md", "role": "task_spec"}, {"path": "/input/materials/paper.txt", "role": "source_material"}],
  "uncertainty": ["材料未给器件稳定性数据，耐久性表述仅限源文一句"],
  "verification": {"check_report_path": "/app/work/check_report.json", "added_numbers": 0, "strong_word_escalation": 0, "caveats_missing": 0, "advice_escalation": 0, "causal_escalation": 0, "extrapolation_escalation": 0, "genre_pass": true},
  "budget": {"model_requests_used": 7, "elapsed_seconds": 310}
}
```
