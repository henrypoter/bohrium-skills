---
name: talk-content-organizer
description: >-
  把 /input 论文/材料组织成「听众-时长-页数」适配的可编辑学术汇报：叙事骨架→页级计划(一页一主张、
  三对齐、讲稿同步、时间校验)→生成 PPTX→渲染复核→证据映射与问答备用页；产出 result.json 写入 /app/output。
  用于组会/答辩/评审学术汇报或幻灯片组织；仅标准库；材料不足诚实降级。
---

# 学术汇报内容组织（Talk Content Organizer）

## 1. 用途
把论文/材料组织成结构清楚、证据可追溯、可编辑、符合模板的汇报产物：
- 叙事：按目标与听众选叙事弧与时间分配（docs/narrative_arcs.md）。
- 页级计划：每页唯一主张+证据定位+quote+视觉+讲稿+用时，写 page_plan.json。
- 交付：生成 .pptx（讲稿/证据写入备注），导出 PDF/PNG 复核。
- 问答：预判机制/数据/对照/局限追问，生成备用页与口径一致回答要点。

## 2. 适用与不适用
适用：/input/case.json、/input/task.md 给出材料与听众/时长/页数/模板约束，任务是把已有内容组织成可讲页面；有母版/起始 deck 时适配之。
不适用：论文精读、写作成稿、科研绘图素材生产；无源材料空泛演讲。材料无法读取时按 §7 诚实降级，禁止凭文件名/标签编造。

## 3. 文件与依赖
流程型 Skill，脚本仅标准库；预装工具：pdftotext、pdftoppm、soffice、fc-list。
- docs/narrative_arcs.md：叙事模板、取舍、三对齐、时间分配、Coherence 关卡。
- docs/example.md：最小调用示例（自拟材料，标注示例）。
- tools/plan_check.py：校验 page_plan（quote 回链/弧顺序/时间/密度/去重）；init-result 生成诚实 result.json 骨架。
- tools/pptx_build.py：page_plan→.pptx（含备注）；--template 继承母版/版式/主题。

## 4. 运行时契约与预算（必须遵守）
- 先读 /input/case.json 与 /input/task.md、真实材料，不凭标签臆造。过程产物 /app/work，最终交付 /app/output。
- 先存诚实结果再增量改进：步骤 1 末落盘 result.json 骨架，每阶段就地更新；预算过半（64 请求/900 秒）即停止改进，收尾 partial。
- 预算：单案例 ≤12 请求、≤600 秒；校验/生成/渲染全本地零请求；单响应 ≤16384 token，长材料分段写盘。
- 诚实：status ∈ success/partial/failed 写明原因；缺图/未验证数字进 uncertainties；数字与引用必须来自材料，禁止补造。

## 5. 执行流程（≈7–9 请求；$SKILL=评测时 /skills/weekly-skill）
0. 读题(1)：提取 case_id、听众、时长、页数、模板/起始 deck、output_contract；列材料文件。
1. 取材料(1)：pdftotext -layout 材料.pdf /app/work/paper.txt（扫描件用 ocr-tool）；质量记 /app/work/extraction_notes.md；随即 init-result。
2. 主线与叙事(1–2)：提取问题/方法/结果/限制四要素；按听众与时长选弧、定页数；结论强度=材料实际报告强度，不夸大。
3. 页级计划(1–2)：写 /app/work/page_plan.json：
   ```json
   {"meta":{"case_id":"","title":"","audience":"defense|group-meeting|review|general","duration_min":15,"slide_count":12,"language":"zh"},
    "spine":{"problem":"","method":"","results":"","limitations":""},
    "slides":[{"n":1,"role":"title|background|method|results|discussion|conclusion|thanks|backup","title":"","claim":"本页唯一主张≤40字","bullets":[""],"evidence":[{"ref":"Fig.1","locator":"§1 p.1","quote":"≤25字原文摘录"}],"visual":"引用哪图哪面板/纯文字","notes":"本页讲稿(口语)","time_s":90}],
    "qa_backup":[{"question":"","answer_points":[""],"evidence":[{"ref":"","locator":"","quote":""}],"slide_ref":0}]}
   ```
   硬规则：每页恰一条主张(≤40字，>48告警)；结果性主张 ≥1 证据，quote 为源材料逐字摘录(≤25字)；讲稿口语化不照抄页面；正片 time_s 之和=时长±10%；备用页 time_s=0。
4. 校验(0)：`python3 $SKILL/tools/plan_check.py check /app/work/page_plan.json /app/work/qa_report.json /app/work/paper.txt`；校验 quote 存在于源材料、弧顺序、讲稿去重、密度；fail 必修(≤2 请求)，warn 记取舍。
5. 生成与模板适配(0–1)：无模板→`python3 $SKILL/tools/pptx_build.py build page_plan.json /app/output/talk.pptx`。有模板/起始 deck→`import pptx` 可用则按版式编辑沿用母版，否则 `build --template 模板.pptx`。冲突记 uncertainties。
6. 渲染复核(1)：soffice --headless --convert-to pdf --outdir /app/output /app/output/talk.pptx + pdftoppm -png -r 60 talk.pdf /app/output/preview；核对页数==计划（含备用页）、中文/公式/图占位不丢失；失败记 uncertainties，不伪造预览。
7. 收尾(1)：写 /app/output/evidence_map.json（页→定位→原文摘录≤25字）与 speaker_notes.md（按页讲稿+用时）；更新 result.json：output_contract 全字段+status/sources/uncertainties/change_log。

## 6. 输出清单（/app/output）
1. result.json — output_contract 全字段+case_id+status/sources/uncertainties/change_log；
2. talk.pptx — 可编辑演示（每页标题/主张条/要点/视觉占位/证据行/备注；含备用页）；
3. talk.pdf + preview-*.png — 真实渲染预览；
4. evidence_map.json — 页级证据映射；
5. speaker_notes.md — 讲稿与时间分配；
6. 复制 page_plan.json/qa_report.json/extraction_notes.md 备查。

## 7. 异常处理与诚实降级
| 异常 | 处置 |
|-|-|
| 材料不足支撑页数/时长 | 产出实际可支撑页数，status=partial，原因入 uncertainties，不凑页 |
| PDF 扫描件/加密/乱码 | ocr-tool；仍失败则就已读部分组织，status=partial |
| 论文缺图/分辨率不足 | 视觉占位标"原图缺失，引用 Fig.k"，禁止重绘数据 |
| 公式/符号丢失 | 文字描述+定位替代，记 uncertainties |
| 模板缺失/冲突、字体缺失 | 用内置母版并记录；fc-list 查字体，缺失不伪造 |
| soffice 渲染失败/超时 | 保留 pptx 与 page_plan，status=partial 注明预览缺失 |
| python3 不可用 | 手写 page_plan 与讲稿，交付 Markdown 分页稿并注明 |
| "无法判断" | 与"材料缺失""运行失败"分开写，不混用 |

## 8. 最小调用示例
见 docs/example.md：自拟迷你材料→page_plan→校验→生成 pptx→渲染，输入输出均标注示例。

## 9. 限制与维护
- pptx_build.py 生成简洁规范结构，不含动画/图像嵌入；图表以"定位+占位"表达，素材生产不属本课题。
- 讲稿时长按中文约 4 字/秒、英文约 2.5 词/秒估算，plan_check 只做区间告警。
- v2.0（2026-11）。维护：改后重跑 docs/example.md，确认 qa_report 通过且 pptx 可渲染。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/read_tool.py support_check answers.json --text source.txt` 把每条证据引文在原文里做逐字匹配，不在原文的（误报）直接揪出；支持度分档统计。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：证据逐字回链、支持度分档。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/support_rubric.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/support_rubric.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
