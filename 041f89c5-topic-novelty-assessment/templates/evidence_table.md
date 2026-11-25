# 选题评估证据与比较模板（v2.0.0）

## A. 最近邻比较矩阵

| record_id | task | method | data | evaluation | conclusion | comparability | 不可直接比较原因 | location | 原文 quote |
|-|-|-|-|-|-|-|-|-|-|
| R1 | 任务T | 方法M1 | 数据D1 | F1 | 原文结论 | partial | 数据划分不同 | 结果第2段 | 逐字摘录 |

## B. 创新差异与证据

| novelty_id | innovation_type | nearest_record_id | dimension | existing | proposed | bounded_claim | status | location | 原文 quote |
|-|-|-|-|-|-|-|-|-|-|
| N1 | data | R1 | data | 已有数据与约束 | 拟议增量 | 仅限本次检索 | supported | 方法第1段 | 逐字摘录 |

规则：场景迁移不得冒充方法创新；`absolute_novelty_claimed=false`；每条差异都回链最近邻，不能以“未检出”代替比较。

## C. 可行性前提

| premise_id | category | statement | status | evidence.type | record_id/case路径 | location | quote/assumption_reason | validation | failure_risk | mitigation |
|-|-|-|-|-|-|-|-|-|-|-|
| P1 | compute | 单卡可运行 | assumption | case_input | /proposal/resources | /proposal/resources/gpu | 输入未给显存 | 单批次显存测试 | OOM | 缩小模型/分批 |

数据、算力、实验、时间、人员五类均须回应。verified 必须有实际来源与 quote；assumption/unknown 必须有验证动作。最终建议须回链问题、创新判断和 feasibility decision。
