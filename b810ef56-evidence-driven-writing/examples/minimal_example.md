# 最小调用示例（自拟短材料，所有文献与数据均为演示虚构，非正式案例结果）

## 输入（自拟材料 snippets.txt）

```
[Paper-A] Li et al., 2023, J. Imag. Mater., DOI 10.1234/jim.2023.001. 原始研究.
"在 25 名受试者的小样本试验中，方法 X 将识别准确率从 71% 提升至 82%（n=25）。"
作者自述局限：样本量小，未做外部验证。
[Paper-B] Wang et al., 2024, 预印本. "我们没有观察到方法 X 在噪声数据上的显著优势（p=0.31）。"
```

任务：写 2-3 句综述段落，说明方法 X 的效果证据现状。

## 调用步骤

```bash
python3 scripts/evidence_lib.py skeleton /app/output   # 1. 生成骨架
# 2. 读材料，填 evidence_library.json / claim_matrix.json，起草 manuscript.md
python3 scripts/evidence_lib.py check /app/output/evidence_library.json \
    /app/output/claim_matrix.json /input/texts /app/output/manuscript.md  # 3. 核验（结构+内容级）
python3 scripts/evidence_audit.py audit /app/output/evidence_library.json \
    /app/output/claim_matrix.json /app/output/manuscript.md  # 4. 强度/摘要/冲突硬闸
python3 scripts/evidence_audit.py fingerprint /input/texts/snippets.txt > /app/work/input_manifest.json
python3 scripts/check_result.py /input/case.json /app/output/result.json
```

## 示意输出（示例）

claim_matrix.json 节选——两条证据冲突，论断判 conflicted：

```json
{"claims": [{"id": "C1", "text": "方法 X 对识别准确率的影响尚无一致结论",
  "verdict": "conflicted",
  "strength_annotation": {"level": "C", "rationale": "正反证据均为初步研究",
    "uncertainty": "样本与噪声条件差异尚未排除"},
  "conflict_analysis": {"summary": "小样本正性与预印本阴性并陈",
    "differences": "样本与数据噪声条件不同", "uncertainty": "无法判定真实效应方向",
    "action": "人工核对全文并补独立重复研究"},
  "bindings": [
    {"evidence_id": "E1", "scope": "partial", "position": "support", "note": "小样本(n=25)正向结果，仅初步证据(C级)"},
    {"evidence_id": "E2", "scope": "partial", "position": "oppose", "note": "预印本阴性结果，未经同行评审(C级)"}]}]}
```

manuscript.md 节选（措辞与 C 级证据对齐、冲突如实并陈）：

> 关于方法 X 的效果，现有证据尚不一致[C1]。一项小样本试验（n=25）报告其将识别准确率从 71% 提升至 82%，但作者指出缺乏外部验证[C1:E1]；另一项未经同行评审的预印本在噪声数据上未观察到显著优势（p=0.31）[C1:E2]。因此目前仅能初步提示其潜在价值，尚需更大样本的重复验证。

result.json 节选：

```json
{"case_id": "demo", "status": "complete", "sources": ["/input/texts/snippets.txt"],
 "uncertainty": [{"claim_id": "C1", "reason": "仅小样本+预印本，证据封顶C级",
   "action": "建议人工补充同行评审文献"}],
 "change_records": ["初稿将C1写为确定性结论，核验后按冲突证据降级并加限定语"],
 "artifact_version": "evidence-driven-writing-1.1.0",
 "input_manifest": {"algorithm": "sha256", "files": [{"path": "/input/texts/snippets.txt", "sha256": "<运行时由 fingerprint 生成>", "bytes": 0}]},
 "verification": {"evidence_lib": {"status": "pass"}, "strength_audit": {"status": "pass"}, "rule_version": "evidence-audit-1.0.0"}}
```
