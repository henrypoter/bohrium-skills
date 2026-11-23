# 共同字段字典（field dictionary）v3

所有文档共用同一套字段定义。工单（comparison-workorder.json）指定维度优先；新增维度按工单定义抽取，字段名保持工单原文。

| 字段名 | 定义 | 取值规则 |
|-|-|-|
| research_object | 研究对象/体系（材料、催化剂、模型等） | 用原文术语，附配方/型号 |
| data_source | 数据集名称+版本+样本量+划分；实验类为样品与来源 | 名称+版本+规模一并记录 |
| method | 方法设置：制备/模型/算法、基线或对照 | 对照设置随方法记录 |
| condition | 实验/评价条件：温度、光照、浓度、pH、预算等 | 条件写全，是可比性判定依据 |
| metric | 评价指标名称与口径定义 | 写清口径（如“去除率=...”），不只写缩写 |
| metric_value | 指标数值 | **unit 与 caliber 必填**；context 填数据集/材料/条件 |
| main_conclusion | 主要结论 | 方向（提升/降低/无差异）与强度（数值/倍数/显著性）分开写 |
| limitation | 作者声明的局限或适用范围 | 只记作者声明的；读者怀疑写进 relations.explanation |

## caliber 口径六维（可比性判定依据）

`task`（任务）、`metric`（指标口径）、`unit`（单位）、`object`（材料/体系/数据集）、`condition`（实验条件，含 pollutant 目标物）、`budget`（剂量/算力/时间）。取值归一化：单位规范简写（%、min-1、mg/L）、指标规范小写名；脚本按归一化字符串机检差异。单位可换算（mg/L↔g/m³）→ 先换算、explanation 写明过程再判 comparable；口径不同 → noncomparable + blocking_dims + 理由；缺失 → unreported。保留原值，禁合并/平均/排名。

## 单元格四态（value_state，必填）

| 状态 | 含义 | 参与投票 |
|-|-|-|
| reported-positive | 报告了阳性/数值结果 | 能 |
| reported-negative | 明确报告阴性/无效 | 能 |
| not-applicable | 该维度对本实验不适用 | 只展示 |
| （无卡）= not-reported | 未报告 | **禁止**（机检告警） |

## 分歧归因枚举（conflicting 必填 attribution）

`sample`（样本/数据集）/ `method`（方法或对照）/ `condition`（实验条件）/ `metric`（指标口径）/ `unit`（单位）/ `unattributable`（排查后仍无法归因，须 ≥20 字排查说明）。

## 证据卡纪律

1. 一卡一值；quote 为原文片段（≤40 字，可截断），paragraph_id 必须存在于 corpus_index.json；
2. 未报告 = 不抽卡（validate 自动列入 gaps），禁止用常识或他文值补空；
3. 图/表读数：confidence="inferred"，note 写“图/表 X 读数，近似”；
4. 同一字段多个取值（多数据集/多条件）：每值一张卡，context/caliber 区分。
