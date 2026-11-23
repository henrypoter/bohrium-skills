---
name: sci-schematic
description: 从科研材料生成可溯源、可继续编辑的科研示意图：材料→元素清单(source={locator,quote})→分层可编辑 SVG→真实渲染→六类检查点校验（实体逐字命中+quote双通道锚定+required覆盖+端点/方向+图例精确+空间/导出），缺失或冲突时诚实降级，绝不臆造。
---

# sci-schematic：来源绑定的科研示意图生成与编辑

把实验流程、机制链、结构包含/并列关系从 `/input/` 材料转成可投稿示意图：每个实体、箭头方向、数值单位必须能回溯到实际材料。适用机制图/通路/流程图/结构层级图与保源编辑；不适用统计方法、海报版式、艺术插画。**先读实际文件，不从文件名或标签臆测。**

## 预算与停止（写死）
- 每案例 **≤12 请求、≤600 秒**：读材料+抽取 3 → elements.json 1 → 修订 ≤3 → 机动 2；构建/校验/渲染/自查走脚本（0 请求）。
- 先落盘诚实 result.json 再增量改进；耗尽时 `status:"partial"` 收官。
- **先修 fail 再修 warn；`figure.score≥90` 或剩余 warn 可解释即停**；每轮只改 trace_report 指出的项。

## 步骤（/app/work 工作，/app/output 落盘）
1. 读 `/input/case.json`、`task.md` 与随案材料（PDF 用 pdf-render，字体用 font-discovery）；记实际文件名。
2. 抽取 elements.json：复制 `templates/pathway.template.json` 照改。硬性：
   - 每 node/edge/group 带 `source={"locator":"文件[:L行[-L行]|:C起-C止]","quote":"材料逐字≤30字"}`；quote 须逐字存在于材料且落在 locator 区间（编造/错位=fail）。
   - `required` 逐项列 task.md 点名必做图元（题面无点名才 `[]`）；缺项/未声明=fail。
   - 图例 `"auto"`；缺失入 `uncertainties`，取舍入 `change_log`，不编造。
3. 构建：`python3 scripts/build_svg.py elements.json /app/output/figure.svg`（分层 layer-groups/edges/nodes/legend、真实 `<text>`、`data-source`；边端点按 assets/edge_rules.json：activates/flows=三角箭头，inhibits=T 形，contains/unknown=虚线无头）。
4. 校验：`python3 scripts/check_figure.py figure.svg elements.json 来源文件...` → `trace_report.json` + `figure_map.md`。**随后立即落盘 result.json。**
5. 修订 ≤3：只改报告指出的问题（拼写/quote/locator/缺项/重叠/越界），重跑 3–4。
6. 渲染：`python3 scripts/render_preview.py figure.svg preview.png figure.pdf > render.json`（无后端报 preview_unavailable）。
7. 组装：`python3 scripts/make_result.py case.json trace_report.json /app/output/result.json --elements elements.json --svg figure.svg --render render.json --png preview.png --pdf figure.pdf`（contract 逐键填真实产物、outputs/deliverables 按角色、sources 摘要、uncertainty/change_log 透传、status 只降级）。
8. （推荐）`python3 scripts/selftest.py`（正向零误杀+13 类变异）。

## 六类检查点（判据外置 assets/*.json；exit 0=无 fail / 1=needs_confirmation）
1. **ENTITY**：节点/边标签与数值+单位必须在来源出现（空白折叠、连字符换行两种解读、大小写不敏感）；未命中给 difflib top-3。
2. **SPATIAL**：节点重叠、越界、必需图层存在。
3. **ENCODING**：marker-end==edge_rules 端点（杀抑制画成激活）；标记端落在 `to` 侧（杀上下游颠倒）；节点色取自 palette。
4. **ANNOTATION**：图例 data-key == 实际用到的 kind∪type；units_notes 留证。
5. **SOURCE**：data-source 非空；required 覆盖审计；quote 双通道（在材料存在→否则 quote_not_found；落在 locator 区间→否则 locator_mismatch）。
6. **EXPORT**：SVG well-formed、含可编辑 `<text>`、画布尺寸；PNG/PDF 证据由 render_preview 提供。

figure.score=100−加权扣分（ENTITY25/SPATIAL10/ENCODING20/ANNOTATION10/SOURCE25/EXPORT10，warn−1 封顶−5）；verdict≠pass 时 status_ceiling=partial，result.json 禁写 answered/complete。

## 输入 / 输出
- 输入：`/input/case.json`（case_id、output_contract）、`task.md`、随案材料。
- 输出 `/app/output/`：figure.svg + figure.pdf/preview.png + trace_report.json + figure_map.md + result.json。

## 异常处理（诚实降级，永不伪造）
缺图注/拼写不定/单位不明/材料冲突/方向不明/字体缺失/渲染全不可用/预算耗尽 → 记 uncertainty+change_log 或降级 partial；quote 编造/错位→回原文复制并改 locator，材料确无则删元素；必做项做不了→required 保留判 missing→partial。

## 最小示例（自拟，非正式案例）
来源句（`/app/work/demo_source.txt`，单行=L1）：`A kinase phosphorylates B at 25 °C; phosphorylated B inhibits C.`；清单 `examples/elements.example.json`（A→B activates、B→C inhibits、25 °C 双通道、required 已声明）。调用：
```bash
python3 scripts/build_svg.py examples/elements.example.json /app/work/demo.svg
python3 scripts/check_figure.py /app/work/demo.svg examples/elements.example.json /app/work/demo_source.txt
python3 scripts/render_preview.py /app/work/demo.svg /app/work/demo.png /app/work/demo.pdf > /app/work/render.json
python3 scripts/make_result.py /input/case.json /app/work/trace_report.json /app/output/result.json --elements examples/elements.example.json --svg /app/work/demo.svg --render /app/work/render.json --png /app/work/demo.png --pdf /app/work/demo.pdf
```
预期：六类全过、quote 区间内命中、score=100；A→B 三角箭头、B→C T 形抑制符；无渲染后端时诚实报 preview_unavailable。

## 限制与维护
分层确定性布局（上游在左）；>40 节点拆子图。校验为字符串/字形/几何级，科学判断由人工/Judge 复核；PNG 为预览级，期刊位图以 SVG/PDF 为准。仅 Python≥3.9 标准库+预装工具；改语法/配色只编辑 assets 两个 JSON；改脚本后必跑 selftest.py。

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
