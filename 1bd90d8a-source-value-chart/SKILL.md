---
name: source-value-chart
description: >-
  Source-bound scientific chart builder/editor (bar/line/scatter/box/heatmap,
  multi-panel). v17 value-level mapping: every glyph records row/col/value/pixel
  geometry/sha256 and audit verify_map independently re-checks value domain,
  geometry proportionality and legend-series 1:1; export_spec verifies
  dpi/sRGB/font-embed/size in PNG/PDF/SVG; SVG keeps editable <text> (no
  text-to-path); entity names and quote anchors are verified verbatim
  (typo -> exit 2); required-figure coverage gate; figure.score stop rule.
  科研数据图表生成与编辑。
---

# source-value-chart：数据→图元值级可回溯 + 逐字核验 + 导出规范的科研图表 Skill

## 用途与条件
从 `/input` 真实数据表(csv/tsv/md)生成/重绘科研图表(bar/line/scatter/box/heatmap/多面板)。
目标是“画得像且准”：每个图元可回到源数据的行列与数值。不负责统计计算与显著性推断。

## 运行时契约与预算
工作 `/app/work`，产物 `/app/output`，必须写 `result.json`(含 case_id/status/status_reason/
answer/sources/validation/uncertainty/change_log)。每案例 ≤12 模型请求、≤600s；脚本 0 请求。
不预制答案；数值只取实际源表。

## 执行步骤
1. **勘察**：`python3 scripts/inspect_materials.py /input --out /app/work/materials_report.json`
   （表头/行数/数值列/单位/CJK 字体）。列名从这里逐字复制。
2. **读题+填 spec**：读 task.md，列必做图清单存 `/app/work/required_outputs.json`；复制
   `templates/chart_spec.example.json` 改列名/系列值/单位；`error.kind` 照源表(sd/se/sem/ci)；
   每个映射可挂 `"quote"`（数据表头逐字片段）。双通道核验：quote 须在文件头存在且含所引列名。
3. **渲染+校验**：`python3 scripts/build_figure.py --spec /app/work/chart_spec.json
   --outdir /app/output/<fig_id> --styles templates/styles.json`
   产出 svg/png/pdf + plot_source.py + mapping_report.json + figure_map.md + validation.json。
4. **verify_map 复核**：`python3 scripts/audit_outputs.py --outdir /app/output
   --require /app/work/required_outputs.json --result /app/output/result.json`
   （缺项/值级错配/导出参数不合 → exit 3，status 强制 partial）。
5. **汇总**：补 result.json 的 answer/changes；读 validation.json `figure.score`，先修 error
   再修 warn，score≥90 或剩余 warn 可解释（理由入 changes）即停。

## 值级判据（本 Skill 的硬门控）
- **逐图元映射 v17**：mapping_report.json 每个图元记录 source(file/columns/rows)、value、
  dx/dy、value_column、pixel_x/pixel_y/pixel_y0/pixel_h(bar)、source_sha256(整文件)、
  field_sha256(所渲染字段)、hash_columns；panels 记录 ylim/xlim/axes_bbox 与 legend_labels。
- **verify_map 三重确定性复核**（audit 独立重读源表，非自说自话）：
  ① 值域：图元 value 必须等于源表(row,col)重读值且 ∈ 该列值域；field_sha256 不一致=源已变；
  ② 几何：由 ylim+axes_bbox 重算 pixel_y/pixel_h，与记录值偏差 > 容差(2px+1%) → fail；
  ③ 图例：legend_labels 与图元 series 一一对应(无 missing/unused)，且逐字命中源系列列值。
- **export_spec**：dpi=300、色彩空间 sRGB(PNG 注入 sRGB chunk)、字体嵌入(type42/SVG
  font-family)、成品尺寸(width/height/viewBox/MediaBox/pHYs)均在导出后校验。
- **文字不转曲**：SVG 用 `<text>` 承载标签，svg.fonttype=none；校验 `<text>` 计数>0 且
  font-family 声明。
- **实体逐字/quote 锚定/覆盖审计**：列名/系列值拼写错 → exit 2 + difflib 建议；quote 错配 →
  exit 2；每有效行必须被渲染(unrendered_rows=error)；任务点名的必做图缺一不可。

## 六类检查点（validation.json）
entity(实体逐字/quote)、spatial(几何比例/刻度)、encoding(值域/零基线/色板)、
annotation(单位/图例/误差线含义)、source(sha256/字段 hash/覆盖率)、export(export_spec/文字)。

## 输入 / 输出
输入：`/input/case.json` + task.md + 材料。输出：`/app/output/<fig_id>/` 下 svg/png/pdf、
plot_source.py、mapping_report.json、figure_map.md、validation.json；根目录 output_audit.json、
result.json。依赖：Python3 标准库 + numpy + matplotlib。

## 异常处理
缺列/实体拼写/quote 错配/源缺失 → exit 2 + validation.json；空值跳过并计数；单位不明不猜；
CJK 字体缺失回退 Noto CJK/文泉驿/Droid，全无则 warn；导出失败保留已生成格式并如实报缺；
数据与任务冲突以源数据为准记 change_log。

## 最小示例（自拟材料，非官方案例）
`templates/chart_spec.example.json` 已填真实 demo 数据（demo_bar.csv 分组柱状 + demo_line.csv 折线）：
```bash
cd /skills/weekly-skill
python3 scripts/build_figure.py --spec templates/chart_spec.example.json --outdir /tmp/example_out/fig1 --styles templates/styles.json
echo '{"required":[{"figure_id":"fig1","chart_type":"bar"}]}' > /tmp/req.json
python3 scripts/audit_outputs.py --outdir /tmp/example_out --require /tmp/req.json  # exit 0
```

## 限制与维护
图型限 bar/line/scatter/box/heatmap；单图内禁双 y 轴；不重算统计量。改样式加
`templates/styles.json` 预设(可 `inherits`)；新图型在 build_figure.py 增分支并补检查点。
版本 v5.0 (2026-11)。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/fig_tool.py svg_check figure.svg` 查文字是否转曲、尺寸是否缺失、是否空图；`element_map` 查每个元素是否映射到来源数据。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：文字不转曲的可编辑源、元素-数据映射、导出前合规检查。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/figure_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/figure_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
