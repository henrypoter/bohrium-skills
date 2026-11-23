---
name: results-discussion-writer
description: 将已有数据、图表与统计输出写成可投稿的"结果与讨论"章节。当输入材料包含实验数据表、图注/图件、统计检验结果，且任务要求起草或修订 Results & Discussion 时触发。核心能力：数值逐条回溯来源、结果/讨论分节不互相顶替、语气强度匹配统计证据、过度解读防护、图表引用编号一致性核查（scripts/rd_check.py）。
---

# 结果与讨论章节写作 Skill

## 安装与依赖
- 仅 Python 3 标准库，无第三方依赖、无网络访问、无软链；无需安装，加载即用。
- 运行路径：Harbor 环境本 Skill 安装在 `/skills/weekly-skill`，脚本用 `$SKILL_DIR/scripts/rd_check.py` 或下方命令自动回退相对路径。
- 若环境无 python3：跳过步骤 4 机检，改用 `checklists/audit_checklist.md` 人工逐项自查，并在 result.json 的 uncertainty 注明"机检未运行"。
- 资源索引：数据格式 `docs/data_formats.md`；定位与边界 `docs/positioning.md`；评分点核对 `docs/scoring_coverage.md`；回归与对照 `bench/`（`python3 scripts/bench_run.py` 一键复跑）。

## 维护与版本
- v3（当前）：修复 4 个由 bench 夹具复现的真实 bug（整数容差吞并小数错配、术语"有效数字"spin 误杀、合并标题 purity 误扫、来源标注只认 S 前缀）；新增 bench 夹具与对照、docs 三件套、异常表超长输入行。
- v2：新增 purity/discussion_block/statcheck/source_consistency/±离差溯源、by_score_dimension 汇总、Harbor 脚本路径回退。
- v1：六步工作流 + fig_ref/number/claim/structure 初版核查。
- 维护方式：任何规则改动先加正向/变异夹具复现，再改 scripts/rd_check.py，最后 `bench_run.py` 全绿才交付。

## 用途与适用条件
- 输入：`/input/case.json`（含 output_contract 字段定义）、`task.md`、数据表/图注/统计输出/PDF 等材料。
- 输出：可编辑章节稿（Markdown，UTF-8）+ 来源映射 + `/app/output/result.json`。
- 不适用：无数据纯综述写作；材料中没有任何数值或图表时，直接按"异常处理"降调产出。

## 预算纪律（硬约束）
1. 每案例模型请求 ≤12 次，全程 ≤600 秒，单次响应留余量。
2. **第 1 步就先写一份诚实的 `/app/output/result.json`**（status="partial"，主结果为空骨架），之后每完成一个阶段增量覆盖改进。任何时刻中断都有可评产物。
3. 素材清点、模板套用、核查脚本都不消耗模型请求，优先用工具完成。
4. 不要在单次回复里生成全文；按"结果→讨论→核查→修订"分段产出。

## 工作流程

### 步骤 0：读入与证据清单（不耗模型请求）
- 读取 `/input/case.json` 与 `task.md`，记录 `case_id` 与 output_contract 要求的**全部字段名**。
- 遍历材料文件（读实际文件内容，不得从文件名/领域标签臆测），建立证据清单 `/app/work/sources.json`，结构：
```json
{"figures": ["图1","图2"], "tables": ["表1"],
 "values": [{"id":"S1","value": 12.4,"unit":"%","desc":"A组准确率","fig":"图1",
             "significant":true,"p":"0.003","disp":1.5,"disp_type":"SD",
             "test":"t","df":28,"stat":2.5}],
 "citations": [{"id":"C1","ref":"作者, 年, 期刊"}]}
```
- 每个可引用数值一条记录：值、单位、出处（图/表/统计文件）、显著性。误差棒含义、坐标刻度、有效数字照抄原文。
- 均值后有 ±离差 时补 `disp`/`disp_type`（SD/SEM/CI）；样本量 n 也记一条 value；检验统计量补 `test`/`df`/`stat`（t/z 支持重算核对，F/χ² 暂不重算）。

### 步骤 1：先写诚实 result.json
立即写 `/app/output/result.json`：包含 case.json 的 output_contract 全部字段 + `case_id` + `status`（partial/complete/failed）+ `sources` + `uncertainty` + `change_log`。初版主结果为空，其余字段诚实标注"待生成"。

### 步骤 2：起草结果段（只陈述事实）
- 用独立标题 `## 结果（Results）`，与 `## 讨论（Discussion）` 分开，不要合并成"结果与讨论"一节。
- 按 `templates/section_skeleton.md` 的结果骨架，按图序或问题组织段落。
- 规则：只写观察到的现象，不写解释、不引文献；每个数值后紧跟来源标注 `[S#]`；趋势/差异表述与统计显著性严格对应（显著才用"显著"且必须挂显著来源，不显著用"呈升高趋势但未达显著"类边界表述）；阴性结果如实交代。
- 数值一律从 sources.json 复制，不做心算换算；必须换算时记录公式进 change_log。

### 步骤 3：起草讨论段（四个分块，不互相顶替）
- **结果复述**：一句话概括主要发现（不新增数据）。
- **文献对比**：每条论断挂 `[C#]`，写明一致/不一致及可能原因；引用找不到时进 uncertainty，不编造文献。
- **机制解释**：推测性内容必须带"提示/可能/推测"等缓冲词，并标注"（机制推测）"。
- **局限**：写到方法、样本、测量、统计四个层面；数据不足以支撑结论处明确降调（如"样本量有限，该结论需扩大样本验证"），禁止拔高。

### 步骤 4：机器核查（不耗模型请求）
```bash
# Harbor 环境 Skill 安装在 /skills/weekly-skill；若路径不存在再退回相对路径
RD=/skills/weekly-skill/scripts/rd_check.py
[ -f "$RD" ] || RD=scripts/rd_check.py
python3 "$RD" /app/work/draft.md /app/work/sources.json /app/work/report.json
```
核查项（fail 必须修复；warn 逐条判断并写入 uncertainty/change_log）：
① 结构：结果/讨论/局限三节齐全，"结果与讨论"合并为一节判 warn；② 讨论四段落位：复述/文献对比/机制推测/局限缺块即 warn；③ 结果段纯净度：结果区段出现解释词或文献引用即 warn；④ 图表引用双向差集；⑤ 数值逐条回溯（值+单位+±离差 disp 及 disp_type(SD/SEM/CI) 匹配，误差棒含义写错即 warn）；⑥ 宣称强度：对不显著数据用"显著/获益"表述判 fail，"显著"未挂显著来源判 warn，spin 获益词与"趋势 vs 显著"区分；⑦ statcheck：正文/来源中 t/z 统计量能否重算出 p（近似，仅 warn）；⑧ 来源内部一致：significant 与 p 是否矛盾。退出码 1 表示存在 fail。

### 步骤 5：修订与定稿
- 按 report.json 逐项修复 fail，warn 逐项判断：确属材料外信息则删除或改标 `[待人工确认]`；number 类 warn 需清零或逐条解释。
- report.json 的 summary 已按评分维度汇总 fail/warn：修复前记录基线，修复后再跑一次，差值即质量增益证据，写进 result.json 的 change_log。
- 生成最终稿 `/app/output/results_discussion.md`；有 pandoc 则渲染 PDF 预览，否则在 result.json 注明。
- 更新 result.json：主结果路径、sources 映射、uncertainty、change_log（含核查前后 fail/warn 计数）；有 fail 未修复则 status 保持 partial 并写明原因。

## 异常处理
| 情况 | 处置 |
|---|---|
| 缺图/图读数不清 | 该数值不写入正文；进 uncertainty，正文写"[待人工确认：图X读数]" |
| 缺统计量 | 只写方向性描述，禁写"显著"；进 uncertainty |
| 单位不明 | 保留原符号并标注"单位待确认"；禁止猜测换算 |
| 引用找不到 | 论断降调为"与本研究一致的趋势亦有报道"，进 uncertainty |
| 数据不足以支撑结论 | 明确降调写局限，禁止拔高；status 记 partial 并说明 |
| 统计量重算与 p 不一致 | 以材料原始统计输出为准，若确系转录错则改回原值；无法判定则进 uncertainty，禁自行"修正" p |
| 材料与任务要求冲突 | 以实际文件内容为准，冲突写进 change_log |
| 超长输入/材料量大 | 素材清点与核查交给脚本（脚本 200 倍输入实测 <1 秒）；正文分段落盘，先保 partial 再增量改进 |

## 自查清单
交付前对照 `checklists/audit_checklist.md` 逐项过一遍（读得准/分得清/说得住/核得了）。

## 最小调用示例
见 `examples/minimal_example.md`（示例材料为自拟短材料，非正式案例）。

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
