# 最小调用示例（示例 / synthetic，非正式案例结果）

以下材料为**自拟合成文本**，仅说明接口与流程，不冒充真实论文或正式案例。

## 1. 合成输入材料 work/demo_paper.txt（2 页，格式同 pdf_text.py 输出）

```
=== PAGE 1 (pdf_obj 4) ===
Abstract. We evaluated enzyme XK-1 for dye decolorization. XK-1 removed
87.3% of Reactive Blue 19 within 30 min at pH 7.0, 25 °C (n=3, mean±SD
87.3±2.1%). This suggests XK-1 may be suitable for textile wastewater.
=== PAGE 2 (pdf_obj 7) ===
Table 1. Decolorization under different pH (30 min, 25 °C)
Group | pH | Removal (%)
A | 5.0 | 41.2
B | 7.0 | 87.3
The thermal stability at 60 °C was not measured in this study.
```

## 2. 合成字段表 /input/target-fields.json（示例）

```json
{"case_id": "demo-001", "fields": [
  {"field_id": "F1", "question": "pH 7.0 时 Reactive Blue 19 的去除率"},
  {"field_id": "F2", "question": "60 °C 下的热稳定性半衰期"}
]}
```

## 3. 调用步骤

```bash
python3 scripts/pdf_text.py paper.pdf work/paper.txt   # 真实案例；示例直接给文本
# 逐字段 grep 定位 → 抄值 → 绑证据 → 判状态 → 写 /app/output/result.json
python3 scripts/validate_result.py /app/output/result.json work/demo_paper.txt
```

## 4. 示意输出 /app/output/result.json（示例 / example output）

```json
{
  "case_id": "demo-001",
  "task": "按字段表抽取酶 XK-1 脱色数据与结论",
  "status": "success",
  "results": [
    {"field_id": "F1", "question": "pH 7.0 时 Reactive Blue 19 的去除率",
     "value": "87.3±2.1", "unit": "%", "statistic": "mean±SD, n=3",
     "condition": "pH 7.0, 25 °C, 30 min, Reactive Blue 19", "comparator": "pH 5.0 组 41.2%",
     "basis": "direct", "status": "reported", "source_type": "text",
     "evidence": {"quote": "XK-1 removed 87.3% of Reactive Blue 19 within 30 min at pH 7.0, 25 °C (n=3, mean±SD 87.3±2.1%).",
                  "page": 1, "paragraph_id": "p1#para1", "table": null, "cell": null, "figure": null},
     "note": "quote 同含数值与统计量；Table 1(p2) row=B × col=Removal (%) 同值复核一致"},
    {"field_id": "F2", "question": "60 °C 下的热稳定性半衰期",
     "value": null, "unit": null, "statistic": null, "condition": null, "comparator": null,
     "basis": "direct", "status": "not_reported", "source_type": "text",
     "evidence": {"quote": "The thermal stability at 60 °C was not measured in this study.",
                  "page": 2, "paragraph_id": "p2#para2", "table": null, "cell": null, "figure": null},
     "note": "原文明确未测量，列为缺口而非填充"}
  ],
  "claims": [
    {"claim_id": "C1", "text": "XK-1 或适用于纺织废水处理", "type": "speculation",
     "cue": "suggests ... may",
     "evidence": {"quote": "This suggests XK-1 may be suitable for textile wastewater.",
                  "page": 1, "paragraph_id": "p1#para1"},
     "related_field_ids": ["F1"]}
  ],
  "sources": [{"path": "work/demo_paper.txt", "role": "main_text"}],
  "uncertainty": ["示例为合成文本，无真实 PDF 版式风险"],
  "gaps": {"not_reported": ["F2"], "source_conflict": [], "extraction_failed": []},
  "change_records": [{"step": 1, "action": "写入骨架 result.json，F1/F2 置 extraction_failed"},
                     {"step": 2, "action": "F1 定位摘要回填 reported；F2 确认未报告"},
                     {"step": 3, "action": "补 claims 并通过 validate_result.py 双重核对"}]
}
```

校验通过标志：`OK: 契约校验通过（含原文双重核对）`。F1 是 `direct`；若问「pH 7.0 比 pH 5.0 高多少个百分点」，value 由 87.3-41.2 推算，basis 必须为 `inferred` 且 note 写算式（`87.3-41.2=46.1`），否则 FAIL。
