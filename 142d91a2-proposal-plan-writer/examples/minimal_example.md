# 最小调用示例（自拟材料，输出为示意，非正式案例结果）

## 1. 示例输入（自捏材料）

`/tmp/demo/case.json`：
```json
{"case_id": "demo-001", "period": "24个月", "budget": "30万元",
 "materials": [
  "Zhang et al. proposed a graph neural network for alloy property prediction, Acta Materialia, 2022, DOI 10.1016/j.actamat.2022.117912.",
  "Wang 等 在 2023 年报道了机器学习辅助高熵合金筛选，金属学报, 2023, DOI 10.11900/0412.1961.2023.00123.",
  "前期实验：本课题组已合成 12 组合金样品，拉伸强度均值 950 MPa。"
 ]}
```
`/tmp/demo/task.md`：`撰写硕士开题报告，24个月周期，含八章与进度甘特表。`

## 2. 调用步骤
```bash
python3 scripts/proposal_scaffold.py init --case /tmp/demo/case.json --task /tmp/demo/task.md --work /tmp/demo/work
# -> init ok: refs=2 priors=1 months=24 budget=30万元
python3 scripts/proposal_scaffold.py gantt --months 24 --items "文献调研@公共:1:4;数据构建@RQ1:3:8;模型开发@RQ1:6:14;实验验证@RQ2:12:20;论文写作@公共:18:24"
python3 scripts/proposal_scaffold.py check --work /tmp/demo/work --draft /tmp/demo/work/draft.md
echo '{"sources":[{"claim":"拉伸强度均值950MPa","source":"case.materials[2]","location":"1.背景"}],"status":"partial","gaps":["材料文献仅2篇"],"uncertainty":["经费口径未给"],"change_log":[]}' > /tmp/demo/work/notes.json
python3 scripts/proposal_scaffold.py finalize --work /tmp/demo/work --draft /tmp/demo/work/draft.md --out /tmp/demo/output
```
draft.md 由模型按 skeleton.md 撰写（略）。硬约定：综述段尾编号 `缺口G1…`；RQ 写 `RQ1（回应缺口G1）`；前期工作挂 `[P1]`；甘特任务挂 `@RQx` 或 `@公共`。

## 3. 示意输出（示例标注，非正式案例结果）

甘特片段（节选前 12 列）：
```
| 任务     | RQ | 起 | 止 |1|2|3|4|5|6|7|8|9|0|1|2|
| 模型开发 | RQ1 | 6 | 14 |.....#########...
```

check 报告（示意，节选）：
```json
{"passed": true, "issues": [], "gaps": ["材料文献仅 2 篇，难撑主题式综述"],
 "rqs": ["1", "2"], "n_refs": 2,
 "matrix": {"RQ1": {"gaps": ["1"], "in_content": true, "in_outcome": true,
            "tasks": ["数据构建", "模型开发"]}}}
```

result.json（示意，节选）：
```json
{"case_id": "demo-001", "status": "partial",
 "deliverables": {"proposal_md": "proposal.md", "check_report": "check_report.json",
                  "evidence_ledger": "evidence_ledger.md"},
 "sources": [{"claim": "拉伸强度均值950MPa", "source": "case.materials[2]", "location": "1.背景"}],
 "uncertainty": ["经费口径未给"], "gaps": ["材料文献仅2篇"], "change_log": [],
 "checks": {"passed": true, "issues": []}}
```
要点：文献仅 2 篇 → gaps 如实标注、status=partial，不编造凑数；台账自动汇总 [R1][R2][P1] 与论断映射。
