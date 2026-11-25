# 图稿规格（figure_spec.md）

## 可编辑性
- 文字保留为 `<text>`，**不转曲**（`svg_check` 会抓"无 text 全 path"）。
- 图层/分组命名可读，便于后续编辑。

## 元素-数据映射
| 元素 | 来源 | 来源定位 |
|-|-|-|
| rect1 | data.csv | A 列 |
| line1 | table2 | 第 3 行 |

图上每个数据点/标签都要能回指到来源；未映射元素会被 `element_map` 抓出。

## 标注与导出
- 图注独立可读：单位、图例、误差线定义、样本量、子图编号。
- 双交付：可编辑 SVG 源 + 真实渲染 PNG；≥300dpi、字体嵌入等只有在实际证据支持时才写 pass，未知写 unknown，不伪造。

## 结构化覆盖声明
除 `required:["实体名"]` 外，对非实体要素使用：
```json
{"id":"req-unit","category":"unit","text":"25 °C","task_quote":"25 °C"}
{"id":"req-panel","category":"panel","svg_id":"panel-a","task_quote":"panel a"}
```
category 支持 entity/relationship/group/legend/annotation/unit/panel。`coverage_guard.py` 要求它们命中实际 SVG；传 task.md 时 task_quote 必须来自题面。

## 文字关系与数据重绘
- `relation_ir.py extract/audit` 只生成明确词法关系候选并核 from/to/type/来源哈希；复杂句人工补，未命中句必须留 uncertainty。
- `data_legend.py sync/audit` 以 CSV entity/category 行更新 node.kind，保持 legend:auto 并记录逐行 data_mapping 和表格 SHA-256；数据更新后必须重跑 sync/build/audit。
- `result.json` 保存 result/spec/figure 版本、输入与产物哈希、复跑命令、覆盖报告和原 output_contract 对齐结果；这些机器证据不替代科学语义复核。
