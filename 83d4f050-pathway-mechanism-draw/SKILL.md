---
name: pathway-mechanism-draw
description: 从生物机制材料生成可溯源、可编辑的分层 SVG 机制图/通路图：五步流程（读材料→定实体关系→定布局图例→出分层 SVG+渲染 PNG/PDF→六类检查点校验+figure.score 收官）。实体名逐字命中材料、evidence {locator,quote} 双通道锚定、渲染回读 PNG 尺寸/非空/元素数、figure_map.md 同交付图上证据与检查记录；判据外置 assets/edge_rules.json。
---

# pathway-mechanism-draw：来源绑定的机制图 / 通路图

## 用途与边界
把机制性文字（信号通路、调控网络、跨膜转运、反馈环）转成可复核通路图：实体、边、定位均可回溯 `/input/` 实际材料。适用线性/分支/反馈环/多区室机制图与保源编辑；不适用统计图表、实验设计、论文版式。**先读实际文件，不凭文件名或标签臆测。**

## 预算与停止（硬性）
每案例 ≤12 模型请求、≤600 秒：读+抽取 3 → 写 spec 1 → 脚本构建/校验/渲染 → 修订 ≤3 → 机动 2；先落盘诚实 result.json，耗尽以 status:"partial" 收官。**先修 fail 再修 warn；figure.score ≥90 或剩余 warn 可书面解释（写 changes）即停。** 扣分配比见 check_pathway.py docstring；status=fail 必修；禁止为追 100 分重写已 pass 的图。

## 五步流程
工作目录 `/app/work`；产出 `/app/output`：pathway.svg + preview.png/pathway.pdf + trace_report.json + figure_map.md + result.json；中间件 `/app/work/spec.json`。

1. **读材料（请求 1–3）**：读 `/input/case.json`、`/input/task.md` 及随案材料（PDF 用 pdf-render/pdf-text），记实际文件名。
2. **定实体与关系（请求 4）**：照 `templates/mapk.template.json` 填 spec.json（schema 见 `_template_note`，词表见 `resources/vocabulary.md`）。三铁律：①实体逐字——label 逐字抄材料（含大小写/连字符）；②required 列 task 点名项一项不漏；③evidence 双通道 `{"locator":"文件:L行[-L行]","quote":"≤30字逐字片段"}`——quote 须在材料存在且落 locator 区间内，编造/错位均硬失败；无方向措辞→unknown；反馈环加 feedback:true。
3. **定布局与图例**：区室按机制流向自上而下（extracellular→membrane→cytosol→nucleus）；受体跨膜，基因/蛋白/复合物/家族成员/细胞类型/区室不混用；图例只从用到的类型∪关系自动派生。
4. **出分层 SVG + 渲染（脚本 0）**：`build_pathway.py spec.json pathway.svg`（layer-title/compartments/edges/nodes/legend/caption、元素带 data-source/data-type/data-label/data-relation）；`render_preview.py pathway.svg preview.png pathway.pdf`（rsvg→inkscape→cairosvg→PyMuPDF，产物核验非空+魔数，全不可用记 preview_unavailable 不伪造）。**渲染回读**：真实 PNG 回读 IHDR 尺寸、非空，并与 SVG 节点/边元素数核对，回读失败 exit 4。
5. **六类检查点 + 收官（脚本 0）**：`check_pathway.py spec.json pathway.svg trace_report.json task.md 材料... [--png=preview.png --pdf=pathway.pdf]`（渲染成功才传）。合成 **figure.score（0–100）** 并自动落 **figure_map.md**（每实体/边=图上画了什么+{locator,quote} 锚点+六类检查点通过记录）；结果照 `templates/result.template.json` 写 result.json：outputs 按角色、sources 照抄 summary、changes 写取舍与人工确认。**entity/coverage 硬阻断未清零→status 必须 partial 并照抄缺失清单。**

## 六类检查点
| 类 | 级别 | 硬判据（fail→exit 1） | 并入 warn |
|-|-|-|-|
| ①实体 | hard | 节点名逐字命中（未命中 top-3）；evidence {locator,quote} 双通道（not_found/location_mismatch fail）；required 全上图 | compartment 名逐字、SVG/spec 标签 drift、data-source 非空 |
| ②关系 | advisory | — | marker-end==edge_rules（抑制 T 形≠激活三角）、徽标==edge_rules、带标端在 to 侧、修饰词源支持 |
| ③方向 | advisory | — | 上下游方向一致；上游边需 feedback:true |
| ④图例 | advisory | — | 图例==用到的类型∪关系（missing/unused） |
| ⑤布局 | hard | 重复 id、悬挂边 | 节点重叠/越界、受体跨膜、节点在本区室带 |
| ⑥导出 | hard | SVG well-formed | 分层+字体栈、PNG/PDF 魔数、PNG 回读尺寸、SVG/spec 元素数一致 |

## 异常处理（诚实降级）
无方向措辞→unknown（点线+?）+uncertainty；基因/蛋白同名→按语境定 type 并写 uncertainty；区室缺失→unlocalized+uncertainty；反馈矛盾→有依据才 feedback:true 否则 unknown；同义名→label 用材料名、权威名写 source；材料冲突→用 task.md 指定来源记 change_log；节点>40→拆子图；渲染全缺→preview_unavailable；预算耗尽→partial。

## 限制与维护
确定性分区布局；>40 节点拆子图；校验=逐字溯源+结构/覆盖硬门禁+渲染回读（advisory 不阻断），不做科学判断（人工/Judge 复核）；仅 Python ≥3.9 标准库+环境预装工具；不降级 ImageMagick/MSVG（丢 marker）。维护：新关系改 assets/edge_rules.json 并同步 vocabulary.md；改后必跑 selftest.py。

## 最小调用示例（示例，非正式案例）
自拟材料 examples/demo_source.txt（EGF–EGFR–ERK–FOS 轴）：
```bash
python3 scripts/build_pathway.py examples/pathway.example.json /app/work/demo.svg
python3 scripts/render_preview.py /app/work/demo.svg /app/work/demo.png /app/work/demo.pdf
python3 scripts/check_pathway.py examples/pathway.example.json /app/work/demo.svg /app/work/demo_trace.json examples/demo_source.txt   # 渲染成功追加 --png=... --pdf=...
python3 scripts/selftest.py   # 15 夹具回归
```
预期：checker 报 pass（六类检查点全绿、score=100、figure_map.md 落盘）；EGF→EGFR 圆点结合、EGFR 跨膜、图例仅含用到的类型与关系。

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
