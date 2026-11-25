# 检索与筛选方案模板（v2.0.0）

> 必须在任何题录/全文判定前定稿。此处是空模板，不是正式案例方案。

- Protocol version：`待填`
- Created at（带时区 ISO-8601）：`待填`
- Research question：`待填`
- Framework（PICO/SPIDER/其他）：`待填`
- 适用范围与不适用范围：`待填`

## 1. 问题拆解

| element_id | 概念 | 同义词/缩写 | 受控词 | 歧义及处理 | 检索意图 |
|-|-|-|-|-|-|
| 待填 | 待填 | 待填数组 | 待填数组 | 待填 | 待填 |

## 2. 数据库与完整检索式

| query_id | 数据库/语料 | 接口 | 字段 | 完整布尔检索式 | date_from/date_to | languages | run_at | result_count | 每段意图 |
|-|-|-|-|-|-|-|-|-|-|-|
| 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 实际值 | 待填 |

保留原始检索式，不能只写“检索了 Alpha 相关文献”。空检索填写：分类、采取动作、后续 query IDs。接口失败填写原查询、重试证据和降级范围。

## 3. 纳排标准

| criterion_id | include/exclude/dedup | stage | 可判定条款 | operational_test | priority | reason_code | effective_version |
|-|-|-|-|-|-|-|-|
| 待填 | 待填 | dedup/title_abstract/full_text/both | 待填 | 待填 | 整数 | 待填 | 待填 |

至少明确：研究类型、人群/对象、干预/现象、结局（若适用）、时间、语言、全文可得性及缺失时如何降级。

## 4. 冲突优先级

建议按任务预先定义：`DUP > 明确排除 > 纳入`；同层双人分歧新增裁决 ID，不修改历史票。若任务需要其他优先顺序，必须在筛选前写明，不可为某篇文献临时改变。

## 5. 版本锁定

```text
criteria_sha256 = SHA256(规范化 screening_criteria JSON)
规范化的键排序、无多余空白规则由 syn_tool.py 计算。
```

修改条款后：升 protocol version → change_log 记录 old/new/reason/actor/time → 用相应版本重筛受影响记录。
