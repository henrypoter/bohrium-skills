# 修订说明（科研示意图生成与编辑）

## 针对判对标准的三项新增机检

1. **文字描述 → 实体关系 IR**：`scripts/relation_ir.py extract` 对明确 activates/inhibits/binds/phosphorylates/drives/is converted to 与常见中文关系词生成带来源的 nodes/edges；`audit` 对当前文本重抽并比较 from/to/type，另核材料 SHA-256 和材料外实体。方向翻转、抑制改成激活、虚构实体均给机器错误。
2. **数据表驱动图例重绘**：`scripts/data_legend.py sync` 将 CSV entity/category 逐行映射到 node.kind，保存 data_mapping/data_binding（含表格 SHA-256）并强制 legend:auto；再运行现有 `build_svg.py` 即重绘。`audit` 抓分类、表格摘要、映射行数和非自动图例漂移。重复实体、分类冲突、空值、缺列时 sync 不写下游文件。
3. **真实图面覆盖**：`scripts/coverage_guard.py audit` 不仅让 required 命中 spec，而要求命中实际 SVG 文本/id；结构化 required_elements 覆盖 entity/relationship/group/legend/annotation/unit/panel，核 svg_id/text、类别和 task.md 的 task_quote，auto 图例缺失也直接失败。

以上结果进入 `make_result.py`：coverage 失败强制 partial；result 新增 result/spec/figure 版本、输入与产物 SHA-256、工具版本、复跑命令、覆盖与数据绑定证据，同时保留原 output_contract 逐键交付。

## 文件变化

- 新增：`scripts/relation_ir.py`、`scripts/data_legend.py`、`scripts/coverage_guard.py`、`bench/innovation_bench.py`。
- 增量修改：`scripts/make_result.py`、`scripts/fig_tool.py`（legacy+v2 result schema）、`SKILL.md`、`templates/figure_spec.md`、`templates/pathway.template.json`、`REVISION.md`。
- 原有 `build_svg.py`、`check_figure.py`、六类评分及来源双通道流程未推倒重写；新能力复用其可编辑 SVG、图例和导出链。

## 可靠性与完整性

SKILL 异常表已逐项覆盖：来源缺失、描述矛盾、数据与图例不符、CSV 结构错误、必做覆盖缺失、字体缺失、导出失败、画布问题与预算耗尽。每类均给恢复动作和 status 上限，不把“保留 SVG”当作完整成功。

正向 bench 走通 extract→audit→CSV sync→audit→build→原六类检查（100 分 fixture）→coverage→result；随后真实修改 CSV 分类并重跑 sync/build，断言新图例键出现、旧键消失。变异覆盖关系类型/方向、虚构实体、来源/数据哈希漂移、分类漂移、CSV 错误、required/单位/图例/子图及 task_quote 错配。

## 相对基础 Agent 的边界与增益

基础 Agent 可直接画图或改标签，但往往不能证明文字关系未翻转、数据变化后图例已同步、题面要求的七类元素在实际 SVG 中均存在。本 Skill 把这些动作变成可执行、可重复的判对闸，并留下哈希和复跑证据。边界：relation_ir 是保守词法候选器，不解决指代/省略/跨句机制；data_legend 只处理实体分类，不做统计选择；覆盖检查只能保证“已声明项存在”，声明是否穷尽仍需对照任务。所有机器通过都不等于科学有效，语义仍须人工或原生/LLM Judge。

## 可复现证据（自拟 fixture，不是平台成绩）

```bash
python3 scripts/selftest.py
python3 bench/bench_run.py          # fig_tool 8/8
python3 bench/innovation_bench.py   # 新能力与 v2 schema 35/35
```

未运行平台固定三案例，未编造同输入质量/耗时提升；相对基础 Agent 的实际质量与效率增益由平台对照确定。
