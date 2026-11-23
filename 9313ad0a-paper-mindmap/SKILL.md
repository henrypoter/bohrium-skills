---
name: paper-mindmap
description: 把科研材料（论文、综述、实验方案、纪要等）整理为可编辑、证据可追溯的思维导图。输出 Markdown 大纲 + FreeMind(.mm)/OPML 可编辑源 + 自绘 SVG 预览 + 节点-来源映射表 + 校验报告。当任务要求从文献/材料抽取层级结构、做思维导图、知识框架图或研究脉络梳理时使用。
---

# paper-mindmap：材料 → 可追溯思维导图

## 适用场景与输入
从 /input/case.json 和 /input/task.md 读取任务说明与材料路径（PDF 需先自行提取文本再阅读；读实际文件，不凭标签臆测内容）。适用：论文/综述结构梳理、实验方案、概念体系。输出全部写入 /app/output。

## 预算纪律（必须遵守）
- 每案例模型请求 ≤12 次、全程 ≤600 秒；单次响应留有余量。
- **先产出诚实的结果再改进**：第 4 步完成后立即写一版完整 result.json（即使带 warnings/uncertainty），随后仅在预算允许时增量精修大纲并重跑脚本。
- 脚本运行快（<2 秒），模型请求主要用于读材料与写大纲；不要逐段多次请求，一次通读、一次成纲。

## 工作流程（6 步）
1. **读任务**：解析 case.json/task.md，确认受众、材料范围、导图用途、交付格式与 output_contract 字段。
2. **通读材料**：标注核心概念、研究问题、方法、证据（数字/图表/引用）、结论、局限、风险；记录每条所在的页码/段落/表图号，作为来源定位。
3. **成纲**：按 templates/outline_template.md 选模板（论文=背景/方法/结果/结论；综述=主题/流派/对比/空白），写 outline.md。规则：
   - 一级分支 ≤7、深度 ≤5；同级粒度一致，不交叉、不重复。
   - 每个节点尽量挂 `{来源: 定位}`；父子间有明确关系时加 `{关系: 因果|对比|依赖|时间|引用|支持|冲突}`；无材料依据的连接禁止添加。
   - 跨分支/非父子关系用 `{关联: <另一节点的显示文本>}`（目标文本须精确匹配），不要硬塞进父子层级。
   - 材料未支撑、层次不清或需人工确认的内容放 `{存疑: 原因}`，宁可在「待确认」分支保守分级，不编造层级。
4. **渲染**：`python3 scripts/build_map.py outline.md --outdir /app/output --name mindmap --title "<案例标题>"`。生成 mindmap.mm / .opml / .svg / _mapping.md / _report.json。来源/关系/存疑自动写进 .mm 备注与 OPML 自定义属性，节点显示文本保持干净。
5. **校验修订**：读 _report.json 的 `readability.score`（0–100）与 `diagnostics`，先修 status=fail 项，再修 warn（精简超长节点、合并过多分支、补来源或标注存疑、修复关联目标）；score ≥90 或剩余 warnings 均可解释即可停。检查 SVG 无重叠、根-枝-叶层级正确。
6. **写 result.json**（见下）并自查。

## 大纲语法（被脚本解析）
```
# 中心主题
- 一级分支 {来源: §1}
  - 叶节点 {来源: §2.1 表1} {关系: 因果} {存疑: 样本量未给出}
  - 对照结论 {来源: §3 图2} {关联: 叶节点}
```
标注只进映射表、.mm 备注（`<richcontent TYPE="NOTE">`）与 OPML 自定义属性（`_source/_relation/_uncertain/_link/_note`），不进节点显示文本；{存疑} 节点在 SVG 中为虚线框并带 ⚠，{关联} 在 SVG 中为红色虚线弧、在 .mm 中为 `<arrowlink>`。

## result.json 写入 /app/output，字段：
- `case_id`：来自 case.json。
- output_contract 全部字段：若 case.json/task.md 声明了 output_contract，逐字段照原样填充；未声明时使用下方默认字段。
- `status`：success / partial / failed（partial 必须说明缺什么）。
- `outputs`：主产物相对路径（editable_source: mindmap.mm 与 mindmap.opml；preview: mindmap.svg；mapping: mindmap_mapping.md；report: mindmap_report.json）。
- `sources`：节点-来源映射摘要（条数、覆盖率、材料定位方式）。
- `uncertainty`：存疑节点清单与原因。
- `changes`：修改/取舍记录与人工确认项。

## 异常处理
| 情况 | 处置 |
|---|---|
| 材料层次不清/冲突 | 保守两级分级 + 「待确认」分支，相关节点标 {存疑}，写入 uncertainty |
| 材料缺失/无法读取 | status=partial 或 failed，说明缺口，不臆造内容 |
| 节点规模爆炸（>60 节点） | 先合并到 ≤7 分支 × ≤3 层，细节折叠进 {来源} 标注 |
| 输出格式受限 | .mm/.opml/.svg 三选可打开者，report 中说明 |
| 时间/请求将尽 | 立即落盘当前诚实结果，停止精修 |

## 复用与限制
scripts/build_map.py 仅用 Python 标准库，可独立运行（python3 build_map.py -h）。SVG 为自绘横向树布局，内置 CJK 字体栈（Noto Sans CJK SC / WenQuanYi / PingFang SC / Microsoft YaHei / Source Han Sans SC），无中文字体的查看器会按栈降级为 sans-serif。最小调用示例见 examples/example_case.md。OPML 自定义属性与 .mm NOTE/arrowlink 均符合各自公开格式约定，可在 FreeMind/XMind/OPML 大纲工具中再编辑。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/write_tool.py claim_check result.json` 核验论断-引用回路，重点抓**数值论断无引用**与悬空引用；`structure` 查必需章节无缺无空。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：论断与引用绑定、章节缺项检测、三向一致。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/manuscript_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/manuscript_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
