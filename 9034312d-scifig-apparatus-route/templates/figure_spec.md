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
- 双交付：可编辑 SVG 源 + 真实渲染 PNG；目标 ≥300dpi、字体嵌入只有在有实际导出证据时才可声明通过，否则记录 unknown/partial。

## 装置/路线工单
- `workorder.parameters`：参数状态只能为 stated/not_stated/not_applicable/conflicted；不得用常见默认值补空。
- `workorder.interfaces`：边按接口 id 引用，检查介质、out→in 和端点所属节点。
- `workorder.order_assertions`：检查顺序矛盾/环；`ambiguities` 记录保守选择或未决原因。
- 机检：`python3 scripts/workorder_guard.py audit spec.json <材料...> --require --out workorder.audit.json`。

## 可复核版本
`result.json` 同时保存 result/spec/figure 版本、输入与产物 SHA-256、工具版本、原 output_contract 逐键结果及复跑命令；真实文件缺失保持 null，不用文字说明替代。
