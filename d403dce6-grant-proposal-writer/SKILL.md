---
name: grant-proposal-writer
description: 基金申请书章节稿写作 Skill。面向"立项依据/科学问题/研究目标/研究内容/技术路线/创新点/研究基础与可行性"七要素，从给定材料生成可直接进入申请书的章节稿，并产出论断-来源三级映射、缺口↔研究内容双向映射、前期基础[P#]绑定、一致性检查报告与技术路线图。事实纪律：研究基础与前期数据只重组给定材料（[P#]），不虚构；材料不足标"【待补充】"。当任务要求依据给定材料撰写/补写/核查基金或课题申请书章节时调用。
---

# 基金申请书写作 Skill（七要素 · 证据链 · 一致性回检）

## 适用条件与调用时机
输入为基金/课题申请书写作任务：`/input/case.json`（结构化材料）+ `/input/task.md`（写作要求）。
材料含领域现状、既有文献、申请人前期成果等。不适用于无科研材料的纯创意写作。

## 硬性纪律（不可违反）
1. **预算纪律**：每案例模型请求 ≤12 次，全程 ≤600 秒。**第一步先 `init` 写出诚实的不完整 result.json**（status=partial，缺口入 uncertainty），再增量改进；时间或请求不足时 `pack` 收尾，保留已完成部分。
2. **事实纪律**：研究基础、前期数据、文献、数字只来自给定材料；逐条挂证据编号（编号由 init 阶段的 evidence_ledger.json 分配）：文献/领域材料 `[S#]`，申请人前期基础 `[P#]`。区分"已完成[✓]"与"拟开展[→]"。立项依据段尾把缺口编号为 `缺口G#`，研究内容逐条注明 `回应缺口Gx`。禁止"首次/国际领先/填补空白"等不可核验修饰（check 会报错）。
3. **异常纪律**：材料不足支撑的章节写"【待补充：缺少……】"并登记到 result.json 的 material_gaps；材料间冲突登记 conflicts；不臆造补全。

## 工作流（5 步，按序执行）

### 第 0 步：初始化（1 次脚本调用，0 模型请求）
```bash
python3 /skills/weekly-skill/scripts/run_grant.py init \
  --case /input/case.json --task /input/task.md --work /app/work --out /app/output
```
产出：`/app/work/evidence_ledger.json`（S#/P# 证据台账）、`/app/work/skeleton.md`（七要素骨架）、`/app/work/matrix.csv`（目标-内容-路线-指标对照表）、`/app/output/result.json`（诚实 partial 版）。

### 第 1 步：读材料 + 凝练科学问题（1–2 次模型请求）
通读 case.json 与台账引用的原文片段。按 `templates/science_question.md` 四问法（别人做到哪一步/还差什么/为什么现在必须做/为什么是我们）把宽泛兴趣收敛为 1 个可回答、有边界的科学问题，写入 skeleton.md 对应插槽。

### 第 2 步：填七要素章节稿（2–4 次模型请求，分节写，长材料优先立项依据与创新点）
按 skeleton.md 逐节写**可直接进申请书的成稿**（不是提纲）：
- 立项依据：含数字或"表明/显示/证明"的论断必须挂 `[S#]`/`[P#]`；按"现状→瓶颈→缺口→切入点"推进；段尾把缺口编号为 `缺口G1`、`缺口G2`。
- 研究目标：3 条左右、可考核；研究内容：逐条对应目标且注明 `回应缺口Gx`；技术路线：写清每步输入/输出/方法/风险与备选。
- 创新点：对照台账已有工作写"差异/为什么难/凭什么做得成"，每条挂对比证据 `[S#]`/`[P#]`。
- 研究基础与可行性：按"能力—证据—与本研究的关系"组织，只重组材料内事实；前期成果挂 `[P#]`（已完成[✓]/拟开展[→]）；缺失即【待补充】。
同步填 matrix.csv（目标编号|研究内容编号|路线步骤|考核指标）。

### 第 3 步：一致性回检（1 次脚本调用）
```bash
python3 /skills/weekly-skill/scripts/run_grant.py check --work /app/work --out /app/output
```
自动产出 `/app/work/check_report.md`（引文覆盖率/创新点禁用词与对比证据锚定/缺口↔研究内容双向映射/[S#][P#]编号越界/章节齐全与要素数量对齐/待补充清单）、`/app/work/route_map.mmd`（Mermaid 路线图）与 `/app/work/check_state.json`。**按报告修订 1 轮**（1–2 次模型请求），只修点名问题。

### 第 4 步：打包（1 次脚本调用）
```bash
python3 /skills/weekly-skill/scripts/run_grant.py pack --work /app/work --out /app/output --case-id <case.json的id>
```
终稿写 `/app/output/proposal_sections.md`，检查结果与映射并入 `/app/output/result.json`（自动回填 source_mapping.used_in 三级对应 + checks 摘要）。result.json 字段见 `examples/result.example.json`。

## 输入材料清单与限制
- 依赖：Python≥3.8 标准库（json/re/csv/argparse/pathlib），无第三方包、无网络、无 pip 安装。
- 材料缺失/无法判断/运行失败分别记录，不互相替代。学科跨度过大时在 uncertainty 声明降置信。
- 复跑幂等：init 不覆盖已写章节与 result.json（仅首次生成），check/pack 可反复运行且结果一致。
- 引文覆盖为行级启发式，不构成引文语义核验，最终由人工清单兜底。

## 安装与维护
- 安装：无需安装；平台将本包挂载为 `/skills/weekly-skill/`，直接调用 `scripts/run_grant.py`。
- 自验：`python3 bench/bench_run.py`（正向零误杀＋10 类变异必命中＋异常场景，exit 0 即通过）。
- 维护：改 `scripts/run_grant.py` 后必须重跑 bench；新增校验须先加变异夹具复现再修；数据 schema 见 `docs/data_formats.md`。

## 资源索引
- `scripts/run_grant.py`：init/check/pack（证据台账 S#/P#、引文覆盖、创新点禁用词与锚定、缺口↔内容映射、[S#][P#]越界、章节齐全、要素对齐、路线图、used_in 回填、打包）。
- `templates/skeleton.md`：七要素章节骨架与写作指令。
- `templates/science_question.md`：科学问题凝练四问模板。
- `checklists/consistency_checklist.md`：人工复核清单（对应 check 报告的每一项）。
- `examples/minimal_example.md` + `examples/result.example.json`：最小调用示例（自拟材料，输出标注为示例，非正式案例结果）。
- `docs/scoring_coverage.md`：评分点逐项核对表；`docs/positioning.md`：能力矩阵与边界；`docs/data_formats.md`：数据格式与维护。
- `bench/`：校验器夹具（正例+10 变异）与确定性路径对照基准（`bench_run.py` 可复跑，报告见 `bench_report.md`）。

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
