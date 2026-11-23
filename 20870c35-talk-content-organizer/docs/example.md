# 最小调用示例（示例材料，非平台正式案例结果）

> 以下为**自拟迷你示例**，仅说明接口与完整流程。

## 输入（自拟）

- `case.json`（节选）：`{"case_id":"demo-001","task":"组织成 5 分钟答辩汇报,正片 5 页","output_contract":{"deck_file":"...","evidence_map":"...","render_record":"..."}}`
- 材料 `mini_paper.txt`：§1 候选空间 1.2×10^5、DFT 单点 6 小时；§2 三层 GNN、8000 条标注；§3 MAE 0.12 eV、命中率 87%、提速 10×、仅验证 <50 原子体系。

## 调用

```bash
W=/app/work; O=/app/output; K=/skills/weekly-skill
python3 $K/tools/plan_check.py init-result /input/case.json $O/result.json          # 步骤1: 骨架
python3 $K/tools/plan_check.py check $W/page_plan.json $W/qa_report.json $W/paper.txt  # 步骤4: quote须在paper.txt
python3 $K/tools/pptx_build.py build $W/page_plan.json $O/talk.pptx                 # 步骤5(有模板加--template)
soffice --headless --convert-to pdf --outdir $O $O/talk.pptx                        # 步骤6
pdftoppm -png -r 60 $O/talk.pdf $O/preview
```

## 示意输出（示例）

- `qa_report.json` → `{"result":"pass","fails":0,"warns":5,"slides_main":5,"slides_backup":1,"source_checked":true,...}`（warn=讲稿偏短）。
- `talk.pptx`：6 页（5 正片+1 备用页），每页含标题条/要点/视觉占位/证据行/主张条，备注含讲稿、证据 quote 与用时；LibreOffice 可编辑。
- `talk.pdf` + `preview-1..6.png`：真实渲染，页数与计划一致；`result.json` 收尾 `status:"success"`、`sources` 列定位、`uncertainties` 注明"示例无真实图表，视觉为占位"。

实际案例所有数字与定位须逐字核对自源文件；示例仅演示。
