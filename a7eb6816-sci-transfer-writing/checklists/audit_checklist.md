# 科研成果转化交付前人工终审

## 读得懂
- [ ] 读者背景、阅读目的、渠道与篇幅来自 task，而非自行假设。
- [ ] 首次缩写有展开；公众稿术语有白话解释；类比没有引入材料外事实。
- [ ] 同概念全文只用 canonical，多语言版本术语一一对应。

## 留得住
- [ ] `evidence` 全部 quote 已逐字回原文并带行/字段；required 项全部进入正文。
- [ ] 关键结论、样本、数值、单位、指标口径、比较基准、方法、限定条件、图表、引用齐全。
- [ ] 删除的是重复和背景铺陈，不是阴性结果或证据；每个删除有理由。

## 说得准
- [ ] 每个数字和单位在本句所引证据 quote/surfaces 中逐字存在，没有心算新数。
- [ ] 初步、相关、观察、不确定、不显著证据的强度未升级；推测明确标记。
- [ ] 冲突值已冻结并由人工 chosen，未自行平均或挑选。

## 接得住
- [ ] 完整干净稿可直接使用，review 稿与其只差 `[S#]`。
- [ ] 每段可由 changes 的 draft_segment 定位，before_quote 可回原文；action/reason/evidence_ids 完整。
- [ ] result 含 output_contract 全字段、sources、changes、uncertainty、validation、gain。

## 异常与增益
- [ ] 缺引用、数据冲突、体裁/篇幅冲突、涉密、未发表均按 SKILL 异常表处理。
- [ ] 材料缺失、无法判断、运行失败分开；partial 写具体限制。
- [ ] A/B 同输入、约束、权限、预算；无平台 baseline 时 gain=pending_platform，未把 bench 当正式成绩。
- [ ] `python3 bench/bench_run.py` 为 20/20，evidence/audit/result 实际报告无未解释 fail。
