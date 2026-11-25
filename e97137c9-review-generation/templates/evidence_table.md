# 证据表模板（与 result.json v2.0.0 对齐）

| claim_id | 论断 | claim_kind | certainty | 主题 | record_id | 位置(页/段/表/图) | 原文摘录 quote | support | evidence_strength |
|-|-|-|-|-|-|-|-|-|-|
| C1 | 机制X促进Y | material_fact | suggestive | 机制 | R12 | 结果第3段 | 粘贴可逐字核对的原文 | supports | fulltext |

规则：
- 每条论断至少一行；多条支持/反证拆成多行，同一 claim_id 可重复。
- `record_id` 必须在纳入清单内；位置写到页/段/表/图，不能只写“文中”。
- `quote` 为原文逐字摘录，不能用自己改写的话代替。`support=supports|contradicts|context`。
- `claim_kind=material_fact|inference|unresolved`；推断在 result.json 另写 `inference_basis`。
- `evidence_strength=fulltext|abstract_only|indirect`；后两者不得支撑 `certainty=established`。
- 研究空白必须回链 `basis_claim_ids` 并限定本次检索；冲突证据并列保留，不删反证。
