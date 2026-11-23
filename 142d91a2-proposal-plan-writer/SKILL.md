---
name: proposal-plan-writer
description: 开题报告与研究计划书写作助手。当任务要求依据给定科研材料（课题指南、文献、前期数据）撰写或修改开题报告/研究计划书时使用。功能：八章骨架、主题式综述、缺口↔RQ双向映射校验、前期基础[P#]清单绑定、进度↔RQ甘特、禁用词拦截、证据台账；引用不编造、缺口明标。
---

# 开题报告与研究计划书 Skill

## 预算纪律（必须先读）
- 每案例模型请求 **≤12 次**、全程 **≤600 秒**。
- **先落地后改进**：第 1~3 步后立即写出诚实的 `/app/output/result.json`（可为 partial），再增量润色。
- 机械性工作全交 `scripts/proposal_scaffold.py`（仅标准库），模型只做研读与写作。
- 输入 `/input/case.json`、`/input/task.md`（先实读，勿凭标签臆测）；输出到 `/app/output/`：
  `proposal.md`、`check_report.json`（自检+闭环矩阵）、`evidence_ledger.md`（台账）、`result.json`（契约见下）。

## 工作流（按序执行）
1. **初始化（0 次模型请求）**
   `python3 scripts/proposal_scaffold.py init --case /input/case.json --task /input/task.md --work /app/work`
   产出 `meta.json`（周期/经费/文献 R1..Rn/前期基础 P1..Pn/含数字事实行及来源）与 `skeleton.md`（八章骨架）。
2. **研读材料（1~2 次请求）**：读 task.md 约束与 meta.json；著录只记材料实际字段，缺失标
   `[材料未给]`，**禁止补全或编造**；前期基础只用 priors 清单。
3. **写草稿（2~4 次请求）**：按 skeleton.md 写 `/app/work/draft.md`，硬约定：
   - 八章齐全（背景/综述/问题目标/内容方法/路线/创新/进度/成果）+ 风险章（数据/方法/进度/伦理
     四类，各写触发信号与备选方案）。
   - 综述**主题式** 2~4 段（已知—争议—缺口），段尾把缺口编号 **缺口G1、G2…**；引用 [n] 对应 Rn，
     禁止逐篇罗列与编造。
   - 1~3 个可证伪 RQ1..，**每个 RQ 注明回应的缺口**：`RQ1（回应缺口G1）`；脚本抓孤儿缺口/孤儿 RQ。
   - 每个 RQ 在“内容与方法”有内容块、在“预期成果”有可考核指标（指标/样本/对照/时间点）。
   - **凡提及申请人前期工作必须挂 [P#]** 且 P# 在 meta.json priors 中；清单没有就写
     `【材料缺口：缺前期基础 X】`，禁止虚构。
   - 创新点用**差异陈述**：`相比 [n] 的 X，本方案在 Y 维度…，预期带来 Z`；禁用「国际领先/首创/
     填补空白/重大突破/原创性」等最高级词（脚本拦截）。
   - 材料不足处在正文与 gaps 双标注 `【材料缺口：…】`。
4. **甘特表（脚本）**：
   `python3 scripts/proposal_scaffold.py gantt --months <周期月数> --items "文献调研@公共:1:3;数据构建@RQ1:3:8;模型开发@RQ1:6:14;实验验证@RQ2:12:20;论文写作@公共:18:24"`
   语法 `任务@RQx:起:止`（可 @RQ1,RQ2；非研究任务 @公共）。每个 RQ 须有任务覆盖、每个任务须挂有效
   RQ 或 @公共（脚本双向校验）。表格嵌入“进度安排”章。
5. **自检（迭代 1~2 轮）**：
   `python3 scripts/proposal_scaffold.py check --work /app/work --draft /app/work/draft.md`
   检查：八章缺失、引用越界/作者-年份不匹配（疑似编造）、缺口↔RQ 孤儿、RQ 方法/成果闭环、
   [P#] 越界或未挂、甘特越界与进度↔RQ 双向覆盖、禁用词、TODO 残留；报告含 RQ 闭环矩阵。
   按 issues 修稿后重跑至 passed 或逐条处置。
6. **交付（脚本）**：把来源映射/不确定性/缺口/修改记录写入 `/app/work/notes.json`，然后
   `python3 scripts/proposal_scaffold.py finalize --work /app/work --draft /app/work/draft.md --out /app/output`
   自动生成证据台账（文献[R#] + 前期基础[P#] + 论断-来源映射）。

## result.json 契约（全字段 + case_id）
```json
{"case_id": "来自 case.json，缺失则 unknown", "status": "complete | partial | failed",
 "deliverables": {"proposal_md": "proposal.md", "check_report": "check_report.json",
                  "evidence_ledger": "evidence_ledger.md"},
 "sections_present": {"背景": true},
 "sources": [{"claim": "关键论断/数字", "source": "R3/P1 或材料路径", "location": "章节"}],
 "uncertainty": ["无法确认事项"], "gaps": ["材料缺口清单"], "change_log": ["修改记录"],
 "checks": {"passed": true, "issues": [], "matrix": {}}}
```
status 诚实：材料缺失→partial 并在 gaps 说明；运行失败→failed 写明原因。

## 事实纪律与异常处理
- 著录只用材料原文（refs 为准），引用编号不越界；不新增材料外事实。
- 数字/指标阈值须回溯到 facts 行或文献，无依据写 `[待确认]`；不写 TODO，未完成处用 `【待人工确认】`。
- 文献太少：减少主题数，gaps 标注，禁止编造。前期清单为空：论断标【材料缺口】，禁止虚构。
- 周期过短/指标不可达：标注冲突并给压缩方案。规范冲突/引用无法获取/条件缺失：记入 uncertainty。
- 信息模糊（无课题指南/周期/经费/数据条件）：先输出「待确认条件清单」向用户索要课题指南、
  周期、经费与数据条件；无法获得时按材料能支撑的写，缺失条件列入 uncertainty。

## 最小调用示例与复用资源
- 示例：`examples/minimal_example.md`（自拟材料，输出为示意，非正式案例结果）。
- 复用：`templates/proposal_template.md`（八章模板）、`templates/checklist.md`（检查表与评分锚点）、
  `scripts/proposal_scaffold.py`（Python≥3.8）。
- 文档：`docs/data_formats.md`（全部数据格式与编号约定）、`docs/positioning.md`（能力矩阵与边界）、
  `docs/scoring_coverage.md`（评分点逐项核对）；`bench/`（确定性对照，可复跑）。
- 适用：中文学位论文/基金式开题报告；不替代学术判断（选题与指标需导师确认，change_log 留痕）。

## 安装与维护
- 零安装：仅 Python≥3.8 标准库（argparse/json/os/re/shutil/sys），拷贝即用；无第三方依赖、
  无网络访问、无环境变量。校验 `python3 scripts/proposal_scaffold.py -h` 可用即就绪。
- 维护：判定规则集中在脚本顶部常量（SECTIONS/BANNED/特征正则）与四个子命令；新增学科措辞
  改模板，新增校验改 check 后必须跑 tests/run_tests.py 回归（准入：13/13 通过，正向零误杀、
  变异必命中）+ bench/bench_run.py exit 0。
- 版本：v3（2026-11-16）夹具驱动修复两处误杀（非引用括注年份、风险章前期词）；变更记录见
  SOLUTION.md。

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
