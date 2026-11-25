# 修订说明 v1.1.0（challenge-b810ef56）

## 本轮针对缺口

1. **证据强度标注**：不再满足于一个 A-D 字母。Evidence 新增 `availability`、`evidence_level_reason`、`strength_basis{design,sample_size,replication,consensus,basis_unknown}`；Claim 新增 `strength_annotation{level,rationale,uncertainty}`，Binding 新增 `position`。`evidence_audit.py audit` 以 S1-S8 检查强度理由、依据完整性与等级上限，未知只能显式 null+登记，不能补造。
2. **仅摘要**：`availability=abstract_only` 时证据及相关论断封顶 C；locator/caveat 双标摘要，S2/S3/S7 拦截“摘要冒充全文”和越级。只有题录或权限不足时没有 quote 可锚定，必须 partial+unsupported/uncertainty，不创建伪证据。
3. **证据相互冲突**：冲突论断需 support 与 oppose/mixed 双向证据、`conflict_analysis{summary,differences,uncertainty,action}`，强度封顶 C；正文该论断编号所在句必须出现不一致/相反/冲突等表述。C4 抓“有反向证据仍 supported”，C5 抓只在后文弱化而当前句隐藏冲突。
4. **可核验与版本**：result.json 新增 `artifact_version`、真实材料的 `input_manifest`（SHA-256+bytes）和 `verification`（evidence_lib/strength_audit 双报告与 rule_version）。`check_result.py` 对可访问输入重算摘要；complete 时双核验均须 pass。

## 新增纯标准库命令

```bash
python3 scripts/evidence_audit.py audit evidence_library.json claim_matrix.json manuscript.md
python3 scripts/evidence_audit.py fingerprint <实际材料文件...>
python3 bench/evidence_audit_bench.py
```

Bench：强度/异常 3 个正向零误杀、14 个变异按规则码必中，另有 fingerprint 正向/内容变异2项，共19/19；既有 `tests/run_tests.py` 17/17 与 `bench/bench_run.py` 9/9 亦须保持全绿。

## 相对基础 Agent 的边界与增量

基础 Agent 可以生成看似合理的证据等级或冲突句，但通常没有强制结构让“设计/样本/重复/共识—等级—正文措辞—摘要可得性—正反证据”逐项对齐。本版本的增量是可执行且可失败退出的中间审计，不是多一段写作建议。

边界：脚本不替代全文语义或专家判断，不能自动判定真 RCT、样本量是否充分、撤稿真实性和科学上的因果/冲突；这些必须由实际全文和人工核验填写。baseline/bench 均为自拟确定性流程对照，不是平台白板或基础 Agent 实测，不据此声称平台分数提升。

## 距榜首仍需 PLATFORM 证据

固定三案例上的真实引用正确率、跨学科全文/摘要/权限异常覆盖，以及基础 Agent 对照下的质量与返工改善仍只能由平台 harness 给出；目前不能用自拟 19/19 代替这 12 分差距中的端到端表现。
