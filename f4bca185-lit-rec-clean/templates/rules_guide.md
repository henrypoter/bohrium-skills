# 字段字典与规则维护指南

## 顶层

| 键 | 类型 | 含义 |
|-|-|-|
| `version` | string | 案例规则版本；任何变更都要更新 |
| `fields` | object | 规范字段名 → 字段规则；至少一项 |
| `dedupe.identity_keys` | string[] | 完整科学身份键，必须都在 fields 声明；为空则不自动去重 |
| `dedupe.rule_id` | string | 精确重复合并的规则号 |

## fields.<canonical>

| 键 | 默认 | 含义/边界 |
|-|-|-|
| `aliases` | `[]` | 输入列名；NFKC、去首尾空白、casefold 后匹配。同一 alias 指向两个字段会硬失败 |
| `type` | `string` | `string` / `number` / `integer` |
| `required` | false | 缺失时进入 review；值仍为 CSV 空串 |
| `review_missing` | false | 非必填也要逐条报告缺失时启用 |
| `allowed` | 不限制 | string 归一后的允许值集合 |
| `synonyms` | `{}` | 原写法 → 规范写法；不做模糊相似匹配 |
| `missing_tokens` | 内置集合 | 额外缺失标记；内置含空、NA、N/A、null、not reported、未报告等 |
| `target_unit` | 无 | 数值目标单位；存在时必须配置 conversions |
| `conversions` | `{}` | 原单位 → `{factor, offset}`；公式为 target=original*factor+offset |
| `unit_aliases` | `{}` | 单位排版别名 → conversions 中的键 |
| `implied_unit` | 无 | 仅当案例规则明确声明默认单位时使用，会留 lineage 规则 |
| `decimal_places` | 不舍入 | 非负整数；ROUND_HALF_UP，不是显示层四舍五入 |
| `thousands_separator` | 无 | 明确千分位字符后才移除；不要默认移除逗号（可能是小数点/分隔符） |
| `min`, `max` | 不限制 | 转换后的 Decimal 边界，含端点；越界不截断 |
| `rule_id` | `R-FIELD:<字段>` | 可审计的稳定编号 |

## 数字与输出

- 标量：输出规范值字符串。
- 区间：`<field>="low..high"`，另给 `<field>__low`、`<field>__high`。
- 中央值±误差：`<field>` 为中央值，另给 `<field>__error`；不把 ± 当置信区间，统计语义仍需原文。
- 所有数值经 Decimal；未设 `decimal_places` 时仅去掉无意义尾零。
- 空值不等于 0；无法解析/未知单位的规范值为空，原字面值可从 lineage 找回。

## 去重判定键

1. `identity_keys` 全部非空且相同，是候选重复的必要条件。
2. 所有 fields 的规范化签名也相同，才合并为一条；不同表头、同义写法、等价单位转换后可以相同。
3. 身份相同但任一值不同：所有行保留并产生 `DUPLICATE_CONFLICT`。
4. 身份键不全：产生 `INSUFFICIENT_IDENTITY`，不得凭内容相似合并。
5. 不同 experiment/material/condition/source 即使值相同也不是重复抽取。

## 审核优先级与失效条件

原始值和身份不可被规则覆盖；字段冲突先于换算，换算先于去重。规则只适用于已声明的数字区域和单位语义。温度等仿射换算必须配置 offset；复合量纲、百分比与比例、误差传播不可只按字面单位猜。出现来源冲突时规则停止自动裁决，交人工。
