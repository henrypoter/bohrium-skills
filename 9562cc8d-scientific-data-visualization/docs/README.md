# 科研数据可视化 v2.0.0

## 用途与闭环

从真实 CSV、字段字典和任务目的出发，完成图型推荐、显式清洗、SD/SEM/分位数计算、图注生成、SVG/300 dpi PNG 导出与逐元素回源重绘审计。已完全替换此前错配的数据库查询内容。

Agent 入口、完整 result 合同、异常处置和限制见根目录 `SKILL.md`。所有命令只使用 Python 3.10+ 标准库（当前自测 Python 3.12.4），无 matplotlib、Pillow 或在线服务依赖。

## 四个命令

| 命令 | 真实产物/检查 | 失败例 |
|-|-|-|
| `recommend SPEC.json` | 字段类型、目的、推荐/不推荐理由、render 支持边界 | 连续相关误配分类图、字段不存在 |
| `render SPEC.json` | 可编辑 SVG、300 dpi PNG、figure-data、caption、manifest | 脏值/哨兵、空集、n 不足、类别>8、低 DPI、字体未映射 |
| `schema RESULT.json` | 版本、证据、血缘、七项覆盖、增益协议 | 无图注/定位/版本/not_checked 理由 |
| `audit RESULT.json` | 回源复算全部图值并重绘 SVG/PNG 比字节；轴/色/DPI/尺寸/图注核验 | 改图或改值后即使重填哈希也失败 |

## 正式运行

```bash
TOOL=/skills/weekly-skill/scripts/visual_tool.py
python3 "$TOOL" recommend /app/output/figure-spec.json
python3 "$TOOL" render /app/output/figure-spec.json
# 按原 output_contract 增加 figures/lineage/coverage/gain 等字段后
python3 "$TOOL" schema /app/output/result.json
python3 "$TOOL" audit /app/output/result.json
```

## 最小合成示例（非正式答案）

在提交根目录、Harbor 环境中运行：

```bash
python3 scripts/visual_tool.py render templates/figure_spec.json
```

它读取 `bench/fixtures/sample_data.csv`，按 `unit=mg/L` 筛选、按 `sample_id` 去重、显式排除空值和 `-999`，在 `/app/output` 生成柱状图。实际均值为 treat=12.8、control=8.6，图注给出各组 n=2、SEM 和缺失排除，S07 的 μg/L 不自动换算。该模板是合成例子，不能冒充正式案例。

静态 `bench/fixtures/good_result.json` 只用于 schema 演示，其中占位图路径明确标 `issues/not_checked`；完整动态正向 `render+audit` 由 Bench 完整执行验证，不把占位图当实际产物。

## 图型与数据表

- `scatter/line`：每个点保留 `source_row/x_raw/x_value/y/group`。
- `bar`：每类每组保留 `mean/sd/sem/n/source_rows`。
- `box`：保留 `q1/median/q3/whisker_low/whisker_high/outliers/n/source_rows`。
- `hist`：保留 `bin_start/bin_end/count/source_rows`。
- 构成仅推荐 `stacked_bar` 并标记本渲染器未实现，不假装已出图。

`templates/figure_spec.json` 给出所有必填规格、85 mm 单栏尺寸、300 dpi 和字体下限。中文字体使用 `label_png/tick_labels_png/title_png` 显式降级；SVG 字体嵌入不是自动通过项。

## Bench 与实际目检

```bash
python3 -m py_compile scripts/visual_tool.py bench/bench_run.py
python3 bench/bench_run.py
```

确切结果见 `REVISION.md`。此外应对生成的 PNG 至少目检一次标题/图例/刻度重叠；本轮已据此修复分组散点图顶部留白。Bench 是合成单元测试，不是平台固定三案例或榜首成绩。

## 已知边界

单 CSV、单面板；自动误差只有 SD/SEM，不自动算 CI 或显著性；未实现堆叠柱、双轴、连续色标、比例尺、SVG 字体嵌入、PDF/CMYK。任务如点名这些能力，须用 `resources.yaml` 的实际工具补做并留可复核产物，否则明确 `not_checked`，不得宣称全覆盖。
