# 成稿规格（manuscript_spec.md）

## 章节契约
| 章节 | 必需 | 字数参考 | 关键内容 |
|-|-|-|-|
| introduction | 是 | 300-500 | 背景、缺口、目标 |
| methods | 是 | 400-800 | 可复现的步骤与参数 |
| results | 是 | 400-800 | 与图表一致的数值 |
| discussion | 按题 | 300-600 | 解释、局限、边界 |
| references | 是 | — | 完整条目 |

## 引用绑定规则
- 每条论断挂 `citations`（ref_id + 页/段定位）。
- 数值论断（样本量、%、剂量、P 值）**必须**有引用；常识性内容标 `is_common_knowledge`。
- `ref_id` 必须在 `references` 表内（悬空引用会被 `claim_check` 抓出）。

## 三向一致
正文数值 = 图表数值 = 原始材料数值。不一致记 critical 并引两处。
