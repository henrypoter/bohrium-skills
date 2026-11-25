# 质量评价量表模板（v2.0.0）

> 先按研究设计选择公认量表或明确说明自定义理由；不要用同一套随意问题评价所有设计。本页只是数据结构模板，不是经过验证的医学量表。

- `scale_id / version`：`待填`
- 适用设计：`待填`
- 来源或自定义依据：`待填`

| dimension_id | 判断提示 | 判断集合与数值映射 | 原文 quote | 精确 location | judgement |
|-|-|-|-|-|-|
| 待填 | 待填 | 如 yes=1/no=0/unclear=0 | 待填 | 页+段+句或字段 | 待填 |

总等级阈值（必须先定义）：

| rating | normalized_score 最小值 | 对综合的影响 |
|-|-|-|
| high/moderate/low（或任务适用等级） | 待填 | 待填 |

计算公式：`score = 各维度 judgement 映射值之和`；`max_score = 各维度最大可能值之和`；`normalized_score = score / max_score`。总分、归一化分数与等级由 `quality_check` 重算。

每篇纳入研究必须填写：`record_id/scale_id/scale_version/items/overall/impact_on_synthesis/claim_ids`。低质量不自动等于排除；排除依据必须来自预注册纳排条款。质量评价不足时标 `not_checked`，不得写“质量较高”。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" quality_check /app/output/result.json
```
