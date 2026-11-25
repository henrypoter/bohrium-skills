# 去重与两轮筛选表模板（v2.0.0）

## 1. 去重记录

| survivor_id | duplicate_ids | method | normalized_value | 双方字段证据 | 核对者 |
|-|-|-|-|-|-|
| 待填 | 待填数组 | doi/title_author_year/manual_verified | 待填 | 待填 | 待填 |

DOI 去空白并规范化大小写后相同才可自动合并；题名相似但研究结果、DOI 或作者冲突时必须人工核对，不能误杀同一研究的不同报告。

## 2. 逐条判定

| decision_id | record_id | stage | decision | reviewer | protocol_version | criterion_ids | reason_codes | quote | location | quote/source SHA-256 | decided_at |
|-|-|-|-|-|-|-|-|-|-|-|-|-|
| 待填 | 待填 | dedup/title_abstract/full_text | include/exclude | 待填 | 待填 | 待填数组 | 待填数组 | 逐字待填 | 句/字段待填 | 待填 | 待填 |

- 每篇纳入与排除均有判定、理由码和原文证据；全文不可得且摘要无法排除时记 `undecided/not_checked`，不要强行纳入或排除。
- 双人分歧保留原 decision IDs；新裁决行增加 `resolves_disagreement: true` 和 `adjudicates`。
- 纳入集/排除集由最终判定重算，不手工凑计数。

## 3. 计数闭环

| records_raw | records_unique | duplicates | included | excluded | undecided |
|-|-|-|-|-|-|
| 实际整数 | 实际整数 | 实际整数 | 实际整数 | 实际整数 | 实际整数 |

```text
records_raw = records_unique + duplicates
records_unique = included + excluded + undecided
```

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" screen_check /app/output/result.json
```
