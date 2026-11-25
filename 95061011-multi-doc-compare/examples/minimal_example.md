# 最小调用示例（合成材料，仅说明接口，非正式案例结果）

## 示例输入（合成双文档，模拟工单指定的两篇“论文”）

`/app/work/text/P1.txt`：

```
We synthesized g-C3N4 nanosheets by thermal polymerization.

The degradation of methyl orange (20 mg/L) under visible light reached
92.4% removal in 60 min.
```

`/app/work/text/P2.txt`：

```
TiO2 P25 was used as received.

The pseudo-first-order rate constant for methyl orange (10 mg/L) under
UV light was 0.031 min-1.
```

## 调用步骤

```bash
python3 scripts/index_corpus.py --text-dir /app/work/text --out /app/work/corpus_index.json
# Agent 写 evidence_cards.jsonl / relations.json / case_meta.json（含下方分诊）后：
python3 scripts/intake_audit.py audit --work /app/work
python3 scripts/validate_and_render.py validate --work /app/work
python3 scripts/validate_and_render.py render   --work /app/work
python3 scripts/validate_and_render.py result   --work /app/work --out /app/output
```

## 示意 evidence_cards.jsonl

```json
{"source_document_id":"P1","field":"metric_value","value":"92.4","unit":"%","context":"MO 20 mg/L, vis 60 min","paragraph_id":"P1::p002","quote":"reached 92.4% removal in 60 min","confidence":"direct","value_state":"reported-positive","caliber":{"task":"degradation","metric":"removal rate","unit":"%","object":"MO 20 mg/L","condition":"vis 60 min"}}
{"source_document_id":"P2","field":"metric_value","value":"0.031","unit":"min-1","context":"MO 10 mg/L, UV","paragraph_id":"P2::p002","quote":"rate constant was 0.031 min-1","confidence":"direct","value_state":"reported-positive","caliber":{"task":"degradation","metric":"rate constant","unit":"min-1","object":"MO 10 mg/L","condition":"UV"}}
```

## 示意 case_meta.json：全部文档先做主题/版本分诊

```json
{"case_id":"synthetic-demo","status":"success","contract_fields":{},"uncertainty":[],"change_records":[],
 "document_assessments":[
  {"source_document_id":"P1","relevance":"relevant","version_state":"selected"},
  {"source_document_id":"P2","relevance":"relevant","version_state":"selected"}],
 "visual_gaps":[]}
```

## 示意 relations.json：口径不同 → noncomparable + 阻断维度

```json
[{"dimension":"metric","relation":"noncomparable","documents":["P1","P2"],"blocking_dims":["metric","unit","condition"],"explanation":"P1 去除率%（可见光），P2 速率常数 min-1（UV），metric/unit/condition 口径不同，禁合并","evidence":[{"source_document_id":"P1","paragraph_id":"P1::p002"},{"source_document_id":"P2","paragraph_id":"P2::p002"}]}]
```

若错标为 `comparable`，validate 记 issue `... forced merge?`（告警 exit 0，不阻断），矩阵出现【问题与告警】表，result.json 的 validation_issues 可复核。

## 示意输出

- 矩阵 metric_value 行：P1 格 `92.4 % (MO 20 mg/L, 可见光 60 min) [P1::p002]`，P2 格 `0.031 min-1 (MO 10 mg/L, UV) [P2::p002]`；
- 覆盖度报告：P2 的 main_conclusion 等字段标 NR；gaps 含 unreported 记录；coverage.per_document 给出每篇覆盖率；
- 合成示例 status="success"；真实案例若 PDF 解析失败则为 partial 并在 status_reason 说明。
