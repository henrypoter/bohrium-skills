# 最小调用示例（自拟演示，非正式案例结果）

假设 `/app/work/demo/source.md` 第 1 行只有一句：

```text
在 20 名参与者的初步观察中，指标为 12.5%，该结果不能推断因果。
```

task 要求“面向公众写一段科普，含‘核心发现’小节，不超过 300 字”。先建 `/app/work/demo/project.json`：

```json
{
  "case_id":"demo-001",
  "items":[{"id":"S1","kind":"number","fact_key":"指标","source":"source.md","line":1,
    "quote":"在 20 名参与者的初步观察中，指标为 12.5%，该结果不能推断因果。",
    "surfaces":["20 名","12.5%"],"required":true,"strength":"preliminary"}],
  "terms":[],"resolutions":[],
  "changes":[{"segment_id":"p1","action":"revise","before_quote":"在 20 名参与者的初步观察中",
    "draft_segment":"在 20 名参与者中，这项初步观察的指标为 12.5%；样本有限，不能据此推断因果。[S1]",
    "reason":"保留样本与数值，面向公众压缩并保留因果边界","evidence_ids":["S1"]}]
}
```

`brief.json`：

```json
{"audience":"public","genre":"科普文章","required_sections":["核心发现"],
 "max_chars":300,"target_channel":"internal","confidential":false,"unpublished":false,
 "allowed_abbreviations":[]}
```

复核稿 `review.md`：

```markdown
# 核心发现

在 20 名参与者中，这项初步观察的指标为 12.5%；样本有限，不能据此推断因果。[S1]
```

依次运行三个机检命令：

```bash
T=/skills/weekly-skill/scripts/transfer_check.py
python3 "$T" evidence /app/work/demo/project.json /app/work/demo/evidence_report.json
python3 "$T" audit /app/work/demo/review.md /app/work/demo/project.json \
  /app/work/demo/brief.json /app/work/demo/audit_report.json
# 从 review 仅删除[S1]得到干净稿；填写 result（含case的output_contract全字段）后：
python3 "$T" result /app/output/result.json /input/case.json /app/output/result_report.json
```

前两个命令在本示例设计下应返回 `ok=true`。若把 12.5% 改成 13.0%，`audit` 必报 `number`；若删掉“初步/不能”并写“证明导致”，必报 `claim_strength`；若 quote 改一个字，`evidence` 必报 `verbatim`。正式运行时不得照抄此示例，必须从实际材料重新建底账。
