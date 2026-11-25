# 可复核系统综述模板（v2.0.0）

> 以下为章节与字段说明，不是可预填的正式答案。

## 1. 范围与方案

- case_id、protocol version、检索日期、数据库/语料、时间/语言限制：待填
- 研究问题与适用边界：待填
- 输入、原文、抽取文本和产物版本哈希：见 result.json

## 2. 筛选流程

- records_raw → duplicates → records_unique → title/full-text included/excluded/undecided：由 decisions 实际重算
- 去重依据、每条理由码、双人分歧和裁决：链到 decision/cluster IDs

## 3. 纳入研究及质量

逐篇列比较字段、设计、人群/对象、干预/现象、结局及质量维度证据。缺失填 unknown；未评价填 not_checked。

## 4. 从证据归纳的主题

每个主题写 induction_note、derived_from、claim_ids，再写有边界的综合。事实、推断、不确定分开表达；所有实质论断带 claim ID。

## 5. 冲突证据

链接 conflict IDs，保留 direct/contradicts 两端逐字位置，说明可能解释和是否解决。不可判断就写 not_checked。

## 6. 研究空白与限制

逐条链接 query IDs、排除记录、理由码及受影响 claims。研究空白只对指定数据库、时间、语言和材料范围成立，不写全局“没有研究”。

## 7. 结论

只综合纳入证据能够支持的内容，明确质量评价对确定性的影响、研究边界、未解决冲突和未检查项。

## 8. 复核记录

- 机检命令、版本与退出结果：待填
- change_log：待填
- unchecked/not_checked：待填
- gain：仅有同输入、同权限实际双方结果时填写；否则 not_available + reason
