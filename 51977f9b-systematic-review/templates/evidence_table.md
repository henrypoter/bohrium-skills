# 证据矩阵模板（v2.0.0）

> 本模板只有列定义；不得把示例值带入正式结果。

## A. 论断—原文回链表

| claim_id | kind | theme_id | 有界论断 | record_id | support | page | paragraph | sentence/field | 逐字 quote | quote_sha256 | source_sha256 | 推断理由/不确定性 |
|-|-|-|-|-|-|-|-|-|-|-|-|-|-|
| 待填 | material_fact/inference/uncertain | 待填 | 待填 | 待填 | direct/partial/contradicts | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |

规则：

- 每条论断至少一行；一条引用一行，不能只挂题录或 URL。
- `record_id` 必须在 `records` 且在 `included`；排除文献的原文证据进入筛选表，不进入综合支撑。
- `location` 在 JSON 中保持结构化：`{page, paragraph, sentence}` 或 `{field}`；页/段加句号缺一不可。
- `quote_sha256` 对 quote 的 UTF-8 精确字节计算；`source_sha256` 等于该记录原文件哈希。只改哈希不改原文不能通过 `quote_check`。
- `partial` 应收窄论断，`contradicts` 应进入冲突矩阵；推断和不确定内容不能伪装成材料事实。

## B. 冲突矩阵

| conflict_id | claim_ids | record_ids | 正向逐字位置 | 反向逐字位置 | 可能解释 | resolution | impact_on_claims |
|-|-|-|-|-|-|-|-|
| 待填 | 待填 | 待填 | 待填 | 待填 | 设计/人群/结局/偏倚等待填 | unresolved/resolved | 待填 |

只有一篇纳入研究时，研究间冲突写 `not_checked`，不能写“证据一致”。

## C. 研究空白表

| gap_id | kind | 有界陈述 | query_ids | excluded_record_ids | 实际 reason_codes | claim_ids | bounded_to | not_claimed |
|-|-|-|-|-|-|-|-|-|-|
| 待填 | evidence_of_absence/search_limitation/unchecked | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 不声称全局不存在 |

`evidence_of_absence` 的排除记录与理由码必须能在 `decisions` 中找到。只有检索局限时选 `search_limitation`，不要伪造排除集。

## D. 机检

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" cite_check /app/output/result.json
python3 "$SKILL_ROOT/scripts/syn_tool.py" quote_check /app/output/result.json
python3 "$SKILL_ROOT/scripts/syn_tool.py" theme_check /app/output/result.json
python3 "$SKILL_ROOT/scripts/syn_tool.py" synthesis_check /app/output/result.json
```
