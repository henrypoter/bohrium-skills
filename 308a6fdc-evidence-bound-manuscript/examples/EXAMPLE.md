# 最小调用示例（自拟短材料，仅演示接口；非正式案例结果）

## 1. 示例输入 `materials/exp_notes.txt`

```
实验记录 2024-05-11
细胞系 HeLa，处理组 n = 6，对照组 n = 6。
药物 X 浓度 10 µM 处理 24 h 后，细胞活力降至 42.3%（对照 100%）。
qPCR: TARGET1 表达上调 2.1 fold（p = 0.003，t 检验）。
Western blot 见图 1（材料未附图注）。
```

## 2. 调用步骤

```bash
python3 scripts/manuscript_tool.py extract --src materials --dst /app/work
# -> 带行号文本 + figure_inventory.json（登记「图 1 @ L0005」）；随后撰写 draft.json
python3 scripts/manuscript_tool.py check --draft /app/work/draft.json --report /app/output/check_report.json --materials /app/work
python3 scripts/manuscript_tool.py build --draft /app/work/draft.json --outdir /app/output
```

## 3. 示例 draft.json（示意，非正式案例）

```json
{
 "meta": {"case_id": "DEMO-001", "status": "partial"},
 "title": "药物 X 对 HeLa 细胞活力的影响（示例稿）",
 "abstract": "药物 X (10 µM, 24 h) 处理后 HeLa 细胞活力降至 42.3%。",
 "required_sections": ["Abstract","Introduction","Methods","Results","Discussion","References"],
 "sections": [
  {"heading": "Introduction", "paragraphs": [
   {"kind": "comment", "text": "背景与意义（评述段，不含事实性数值）。", "evidence": []}]},
  {"heading": "Methods", "paragraphs": [
   {"text": "HeLa 细胞分为处理组与对照组（各 n = 6），以 10 µM 药物 X 处理 24 h。",
    "evidence": [{"material": "exp_notes.txt", "loc": "L0002-L0003",
     "quote": "细胞系 HeLa，处理组 n = 6，对照组 n = 6。\n药物 X 浓度 10 µM 处理 24 h"}]}]},
  {"heading": "Results", "paragraphs": [
   {"text": "处理后细胞活力降至 42.3%（对照 100%）；TARGET1 表达上调 2.1 fold（p = 0.003），Western blot 见图 1 [@smith2023]。",
    "strength": "hedged",
    "evidence": [{"material": "exp_notes.txt", "loc": "L0003-L0004",
     "quote": "细胞活力降至 42.3%（对照 100%）\nTARGET1 表达上调 2.1 fold（p = 0.003"},
    {"citation": "smith2023"}]}]},
  {"heading": "Discussion", "paragraphs": [
   {"kind": "comment", "text": "结果提示药物 X 抑制细胞活力，因果关系需进一步实验。", "evidence": []}]}
 ],
 "figures": [{"id": "1", "caption": "", "source": "exp_notes.txt L0005", "caption_missing_in_source": true}],
 "citations": {"smith2023": {"authors": "Smith J, Lee K", "year": "2023", "journal": "J Test Biol",
               "doi": "10.1000/xyz123", "unverified": true}},
 "sources": [{"material": "exp_notes.txt", "loc": "L0001-L0005"}],
 "uncertainty": ["图 1 无图注，待作者补写", "文献 smith2023 取不到全文，元数据未核实"],
 "change_log": [], "human_review": ["确认图 1 图注", "核实 smith2023 DOI"]
}
```

## 4. 示意输出（节选，标明为示例）

- `check`：`1 fail / 若干 warn`——fail 为「图 1 缺图注」；演示异常处理：缺图注不编造，显式列待补项。quote 不在所标 loc 区间、引用清单外图表、数值与引文不符同样报 fail。
- `build`：`manuscript.md/.docx`（可编辑）+ `manuscript.pdf`（渲染预览）+ `evidence_map.md`（段落→材料区间/文献映射）+ `result.json`（含 case_id、status、sources、uncertainty、pdf/docx_status）。
- 图 1 成稿显示 `[CAPTION-MISSING: 材料未提供图注，待作者补写]`，而非编造图注。
