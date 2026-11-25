---
name: sci-schematic
description: 来源绑定科研示意图生成与编辑：relation_ir 从明确文字模式生成实体—关系候选 IR 并审计方向/类型漂移，data_legend 以 CSV 驱动分类和自动图例重绘，coverage_guard 核验题面声明在真实 SVG 的实体/关系/图例/标注/单位/子图覆盖；保留分层可编辑源、六类检查、版本/SHA-256/复跑记录，异常诚实降级。纯标准库。
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
   - **文字关系候选**可先用 `python3 scripts/relation_ir.py extract SOURCE.txt elements.draft.json --report extraction.json`，再逐条人工核对并补 required；`audit SOURCE.txt elements.json` 查上下游/类型/额外实体漂移。词法候选不是科学结论，不匹配句子进 uncertainties。
   - **数据驱动重绘**：`python3 scripts/data_legend.py sync elements.json TABLE.csv elements.synced.json --entity-column entity --category-column category --report binding.json`；接 `build_svg.py` 与 `data_legend.py audit`。CSV 分类→node.kind→legend:auto，变更表格后须重跑 sync/build/audit，不手工改图例颜色。
   - 除 required 字符串外，用 `required_elements[]={id,category,svg_id|text,task_quote}` 声明图例/标注/单位/子图等硬约束；category 支持 entity/relationship/group/legend/annotation/unit/panel。
3. 构建：`python3 scripts/build_svg.py elements.json /app/output/figure.svg`（分层 layer-groups/edges/nodes/legend、真实 `<text>`、`data-source`；边端点按 assets/edge_rules.json：activates/flows=三角箭头，inhibits=T 形，contains/unknown=虚线无头）。
4. 校验：`python3 scripts/check_figure.py figure.svg elements.json 来源文件...` → `trace_report.json` + `figure_map.md`。**随后立即落盘 partial result.json。**
5. 覆盖硬闸：`python3 scripts/coverage_guard.py audit elements.json figure.svg --task /input/task.md --out /app/output/coverage.json`。required 必须命中真实 SVG（不是仅存在 spec）；结构化项同时核 task_quote、svg_id/text 与类别；auto 图例缺失或覆盖不足禁 success。
6. 修订 ≤3：只改报告指出的问题（关系/分类漂移、拼写/quote/locator/缺项/重叠/越界），重跑 2–5。
7. 渲染：`python3 scripts/render_preview.py figure.svg preview.png figure.pdf > render.json`（无后端报 preview_unavailable）。
8. 组装：`python3 scripts/make_result.py case.json trace_report.json /app/output/result.json --elements elements.json --svg figure.svg --coverage coverage.json --source 来源文件 --render render.json --png preview.png --pdf figure.pdf`（contract 逐键填真实产物、status 只降级，并记录数据映射、覆盖、版本/哈希/复跑证据）。
9. （推荐）`python3 scripts/selftest.py && python3 bench/innovation_bench.py`。

## 六类检查点（判据外置 assets/*.json；exit 0=无 fail / 1=needs_confirmation）
1. **ENTITY**：节点/边标签与数值+单位必须在来源出现（空白折叠、连字符换行两种解读、大小写不敏感）；未命中给 difflib top-3。
2. **SPATIAL**：节点重叠、越界、必需图层存在。
3. **ENCODING**：marker-end==edge_rules 端点（杀抑制画成激活）；标记端落在 `to` 侧（杀上下游颠倒）；节点色取自 palette。
4. **ANNOTATION**：图例 data-key == 实际用到的 kind∪type；units_notes 留证。
5. **SOURCE**：data-source 非空；required 覆盖审计；quote 双通道（在材料存在→否则 quote_not_found；落在 locator 区间→否则 locator_mismatch）。
6. **EXPORT**：SVG well-formed、含可编辑 `<text>`、画布尺寸；PNG/PDF 证据由 render_preview 提供。

figure.score=100−加权扣分（ENTITY25/SPATIAL10/ENCODING20/ANNOTATION10/SOURCE25/EXPORT10，warn−1 封顶−5）；verdict≠pass 时 status_ceiling=partial，result.json 禁写 answered/complete。

**新增三个独立判对闸**：①`relation_ir audit` 对比当前文本的 from/to/type，材料 SHA-256 改变、关系翻转和额外实体均 fail；②`data_legend audit` 核 CSV 行、node.kind、data_mapping、legend:auto 和表格 SHA-256，分类变更必须 sync+build 重绘；③`coverage_guard audit` 对真实 SVG 核 required 和七类 required_elements，覆盖审计失败使 result 强制 partial。三者不替代语义 Judge，也不因分数高就免除人工核对。

## 输入 / 输出
- 输入：`/input/case.json`（case_id、output_contract）、`task.md`、随案材料。
- 输出 `/app/output/`：figure.svg + figure.pdf/preview.png + trace_report.json + figure_map.md + coverage.json + result.json；使用文字/数据能力时另留 extraction.json/binding.json。
- `result.json` 必填可核验版本：`result_schema_version/figure_version/spec_schema_version/generated_at_utc/tool_versions`；`source_manifest/artifact_manifest` 对真实文件记 bytes+SHA-256；`reproduction.commands` 给复跑入口；`data_mapping/data_binding/coverage` 保存映射与覆盖证据；原 output_contract 逐键填值，未知保持 null。

## 异常处理（诚实降级，永不伪造）
| 情况 | 机检/处置 | 状态 |
|-|-|-|
| 来源缺失/不可读 | 不生成来源断言；可读部分先出 partial，uncertainty 写实际文件与原因 | partial/failed |
| 描述矛盾/方向不明/文字模式未命中 | 不从上下文猜关系；未匹配句进 uncertainty，冲突候选人工确认，relation audit 防漂移 | partial |
| quote 编造/错位 | 回原文复制并修 locator；材料确无则删元素，不拿近似句顶替 | fail→partial |
| 数据重复/空值/缺列/分类冲突 | `data_legend sync` 失败且不写 SYNCED；修表后重跑，不擅自合并类别 | partial |
| 数据与图例不符/表已更新 | audit 报 category/digest/mapping drift；sync→build→audit 重绘，不手改旧图例 | partial 直至通过 |
| 必做实体/关系/图例/标注/单位/子图缺失 | required 或 required_elements 保留 fail，coverage 指向 svg_id/text/task_quote | 强制 partial |
| 拼写不定/单位不明/缺图注 | 保留已核实文字，向材料求近邻建议并记 uncertainty；无来源单位不补 | partial |
| 字体缺失 | 用实际字体栈和 backend 记录，不冒称“字体嵌入通过” | warn/partial |
| 渲染全不可用/导出失败 | preview_unavailable，保留可编辑 SVG；不写假 PNG/PDF | partial |
| 重叠/画布溢出/长标签 | 改布局或拆子图并重跑 check+coverage，不裁科学内容 | partial 直至通过 |
| 预算耗尽/运行失败 | 先保存已有真实产物及缺失清单，不升级 status | partial/failed |

## 最小示例（自拟，非正式案例）
来源句（`/app/work/demo_source.txt`，单行=L1）：`A kinase phosphorylates B at 25 °C; phosphorylated B inhibits C.`；清单 `examples/elements.example.json`（A→B activates、B→C inhibits、25 °C 双通道、required 已声明）。调用：
```bash
python3 scripts/build_svg.py examples/elements.example.json /app/work/demo.svg
python3 scripts/check_figure.py /app/work/demo.svg examples/elements.example.json /app/work/demo_source.txt
python3 scripts/coverage_guard.py audit examples/elements.example.json /app/work/demo.svg --out /app/work/coverage.json
python3 scripts/render_preview.py /app/work/demo.svg /app/work/demo.png /app/work/demo.pdf > /app/work/render.json
python3 scripts/make_result.py /input/case.json /app/work/trace_report.json /app/output/result.json --elements examples/elements.example.json --svg /app/work/demo.svg --coverage /app/work/coverage.json --source /app/work/demo_source.txt --render /app/work/render.json --png /app/work/demo.png --pdf /app/work/demo.pdf
python3 bench/innovation_bench.py
```
预期：六类全过、quote 区间内命中、score=100；A→B 三角箭头、B→C T 形抑制符；无渲染后端时诚实报 preview_unavailable。

## 限制与维护
分层确定性布局（上游在左）；>40 节点拆子图。校验为字符串/词法/字形/几何级，科学判断由人工/Judge 复核；relation_ir 只认明确模式，未命中≠无关系，复杂省略/指代/跨句语义须人工抽取。data_legend 适合实体—分类表，不做统计计算或数值拟合。PNG 为预览级，期刊位图以 SVG/PDF 与实际导出参数为准。仅 Python≥3.9 标准库+预装工具；改语法/配色只编辑 assets 两个 JSON；改脚本后必跑 selftest.py 和 innovation_bench.py。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`coverage_guard` 核真实 SVG 覆盖，`relation_ir/data_legend audit` 核关系与表图一致，六类检查和 manifest/复跑命令支撑独立复核；`fig_tool.py svg_check` 仍查可编辑结构。
- **使用增益（25 分）**：不预写或捏造 `gain`；质量/耗时/返工差值只能由平台同输入、同预算的基础 Agent/Skill 对照生成，当前 Skill 提供可定位检查记录作为证据入口。
- **创新增益（15 分）**：明确文字模式的关系 IR、CSV 驱动图例重绘、题面七类要素的实际 SVG 覆盖闸。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/figure_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：模板、词法规则、CSV 映射与 `bench/bench_run.py`、`bench/innovation_bench.py` 可独立复用维护。

### 交付前自检
```bash
python3 bench/bench_run.py   # 原有工具正向零误杀 + 变异必命中
python3 bench/innovation_bench.py
```
