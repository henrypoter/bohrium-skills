# 最小调用示例（合成材料，仅演示接口，非正式结果）

## 输入
`/app/work/paper.txt`（合成）：

```
[[page 3]]
本研究在 2024 年采集了 128 份水稻样本，测得平均产量为 7.2 t/ha。

新施肥方案使产量较对照组提高了 15%，差异显著（p < 0.05）。

[[page 5]]
该方法仅适用于粳稻品种，对籼稻的效果尚未验证。
```

论断 `/input/claims-to-verify.json`（合成）：

```json
[{"id": "A1", "claim": "新方案使产量提高了 15% 且对所有水稻品种有效"}, {"id": "A2", "claim": "样本量为 200 份"}]
```

## 调用
```bash
python3 scripts/verify_claims.py selftest   # 自测 10/10 PASS 再开始
python3 scripts/verify_claims.py prep --claims /input/claims-to-verify.json \
    --source /app/work/paper.txt --out /app/work --topk 3
# 阅读 verdicts.draft.json（子论断候选句+alignment 检查表），判定后存 verdicts.json
python3 scripts/verify_claims.py finalize --draft /app/work/verdicts.json \
    --source /app/work/paper.txt --out /app/output --case-id DEMO
```

## 示意输出（示例，节选 result.json）
```json
{
 "case_id": "DEMO", "status": "success",
 "claims": [
  {"id": "A1", "verdict": "partially_supported",
   "sub_claims": [{"sub_id": "A1.1", "text": "新方案使产量提高了 15%", "types": ["fact"]},
                  {"sub_id": "A1.2", "text": "对所有水稻品种有效", "types": ["scope"]}],
   "evidence": [
    {"quote": "新施肥方案使产量较对照组提高了 15%，差异显著（p < 0.05）。", "file": "paper.txt",
     "page": 3, "para": 2, "quote_verbatim": true, "support": "supported"},
    {"quote": "该方法仅适用于粳稻品种，对籼稻的效果尚未验证。", "file": "paper.txt",
     "page": 5, "para": 1, "quote_verbatim": true, "support": "contradicted"}],
   "reasoning": "子判断 A1.1 有原文直接支持；A1.2 与原文适用范围限定冲突，整体部分支持。",
   "numeric_check": "claim 15% == quote 15%（逐字一致）",
   "limits": "效果仅在粳稻验证，'所有品种'为过度外推。", "rule_flags": ["advice:R2_scope_overreach:复核全称量化是否超出原文限定语",
                    "advice:R4_conflict:证据标签并列 supported+contradicted，建议 limits 并列双方定位"]},
  {"id": "A2", "verdict": "contradicted",
   "evidence": [{"quote": "本研究在 2024 年采集了 128 份水稻样本，测得平均产量为 7.2 t/ha。",
     "file": "paper.txt", "page": 3, "para": 1, "quote_verbatim": true, "support": "contradicted"}],
   "reasoning": "原文样本量为 128 份，与论断的 200 份直接矛盾。",
   "numeric_check": "claim 200 != quote 128", "limits": "", "rule_flags": []}
 ],
 "sources": [{"file": "paper.txt", "chars": 136}], "uncertainty": [],
 "summary": {"total": 2, "supported": 0, "partially_supported": 1, "contradicted": 1, "insufficient_evidence": 0},
 "change_records": []
}
```
要点演示：复合论断被拆开；A1 因范围夸大由模型判部分支持（rule_flags 记录 R2/R4 advice）；数值逐字比对写入 numeric_check；引文均逐字命中原文。若把 A1 填成 supported，finalize 只记 advice 提示、不强制改判，终判仍由模型据原文给出（见 selftest 变异夹具 M1）；编造引文则由 quote_verbatim 硬门槛拦截（M4）。
