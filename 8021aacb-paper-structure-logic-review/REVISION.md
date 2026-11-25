# 修订说明 v1.1.0（challenge-8021aacb）

## 本轮针对缺口

1. **是否覆盖研究问题**：新增 `logic_audit.py scan` 抽取 RQ 候选并保留问题句锚点；`verify` 要求每个 RQ 都给方法、结果、结论锚点与判定理由。`closed` 必须四环合法，`open` 必须关联 research_question diagnosis，`not_applicable` 必须解释；Q1-Q4 拦截漏审、错锚和“口头 closed”。
2. **结论与数据范围的边界比对**：新增 CB 候选与结论/results 数值差集，逐条记录 results 数据锚点及 `within/narrower/broader/uncertain`。结果外数值不得判 within/narrower；broader 必须关联结论边界 diagnosis。它不是“无限定词”提示的重复，而是可逐值、逐锚点复核的范围账。
3. **稿件被截断**：由 bool 升级为 signals、last_anchor、last_text_sha256、read_scope、action。疑似截断必须 status=partial，同时登记 material_gaps（读到哪里/缺什么）与 anomalies（为何疑似）；T1/T2 抓静默改哈希、隐瞒截断或继续 success。
4. **可核验与版本**：result.json 新增 `artifact_version`、scan 实际计算的 `input_manifest`（SHA-256+bytes+anchors_version）及 `logic_audit`；logic_audit.json 作为独立交付物，verify 可重跑。result_check 的必需字段清单同步增加，但语义硬闸由 verify 负责。

## 新增纯标准库命令

```bash
python3 scripts/logic_audit.py scan <稿件.md> -o logic_audit.json
python3 scripts/logic_audit.py verify result.json logic_audit.json
python3 bench/logic_bench.py
```

新 bench：3 个正向断言零误杀 + 17 个内容/契约变异全部命中，20/20；既有 `fixture_test.py` 34/34、`bench_run.py` 9/9、`result_check.py --selftest` 亦须全绿。

## 相对基础 Agent 的边界与增量

基础 Agent 往往能概述“全文围绕某问题”“结论基本一致”，但缺少逐 RQ/CB 的可失败契约，容易漏掉第二研究问题、把结果外数字写成既定结论、或截断后仍交付完整状态。本版本把这些笼统自述改为原文锚点、数值差集、诊断编号和输入/末文哈希，提升的是结构级可复核性，不是语言润色。

边界：RQ 词表会漏掉隐含问题，scan 无候选不等于稿件无研究问题；数值不同不必然代表结论错误，单位换算与表格解析仍需人工。脚本只能发现漏裁决、错锚点、自相矛盾记录与可疑截断，不能证明研究设计或科学结论正确。path_compare 是构造的流程对照，不是平台基础 Agent 实测。

## 距榜首仍需的证据

固定三案例上对主要断裂的召回/误报、多研究问题长稿和表格型结果的范围判定、双栏 PDF 实际截断与缺图表处置，以及基础 Agent 同稿同预算的质量/效率对照仍是主要差距；自拟 20/20 只证明工具规则不退化，不能代替榜首 83.0 的平台端到端表现。
