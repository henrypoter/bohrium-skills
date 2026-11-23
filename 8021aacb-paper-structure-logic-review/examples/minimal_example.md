# 最小调用示例（自拟短材料，非正式案例结果）

输入 examples/demo_manuscript.md（自拟）：4 节短稿，含跨章节复述与结论越界。

```bash
python3 /skills/weekly-skill/scripts/skeleton.py /input/demo_manuscript.md -o skeleton.json
python3 /skills/weekly-skill/scripts/result_check.py /app/output/result.json
```

result.json 关键片段（示例；每条诊断带 criterion；L3 只建议不进 change_log）：

```json
{"case_id":"demo-self-made","status":"partial",
 "diagnosis":[
  {"id":"D1","dimension":"redundancy","location":"S2.P1.s2","criterion":"与 S1.P1.s2 同贡献角色且非必要呼应","evidence":"本文研究调度算法，提出一种贪心调度器","type":"跨章节复述","severity":"mid","action":"delete"},
  {"id":"D2","dimension":"conclusion_boundary","location":"S4.P1","criterion":"证据仅覆盖 3 个自建测试集(S3.P1)，结论却表述为普遍因果","evidence":"导致所有数据中心延迟显著下降","type":"结论越界+因果越界","severity":"high","action":"narrow"}],
 "edit_plan":[
  {"id":"E1","action":"delete","level":"L1","anchor":"S2.P1.s2","target":null,"detail":"删除与引言重复的句子","ref_diagnosis":"D1"},
  {"id":"E2","action":"narrow","level":"L3","anchor":"S4.P1.s1","target":null,"detail":"结论收窄到证据范围(只建议)","ref_diagnosis":"D2"}],
 "dimension_plan":{
  "research_question":{"status":"no_finding","diagnosis_ids":[],"edit_ids":[]},
  "section_structure":{"status":"no_finding","diagnosis_ids":[],"edit_ids":[]},
  "argument_chain":{"status":"no_finding","diagnosis_ids":[],"edit_ids":[]},
  "paragraph_relation":{"status":"no_finding","diagnosis_ids":[],"edit_ids":[]},
  "redundancy":{"status":"diagnosed","diagnosis_ids":["D1"],"edit_ids":["E1"]},
  "conclusion_boundary":{"status":"diagnosed","diagnosis_ids":["D2"],"edit_ids":["E2"]}},
 "change_log":[{"anchor":"S2.P1.s2","level":"L1","original":"本文研究调度算法，提出一种贪心调度器。","revised":"（删除）","reason":"与 S1.P1.s2 重复","fact_note":"整句删除为 D1 授权的 delete 动作"}]}
```

说明：以上为自拟样例与示意输出，不代表平台正式案例；正式运行须来自实际输入文件。
