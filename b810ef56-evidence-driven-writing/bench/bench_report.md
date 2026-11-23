# 使用增益对照报告（确定性路径对照）

复跑：`python3 bench/bench_run.py`，结果落 `bench/bench_results.json`，退出码 0。

## 设置

- 同一自拟演示案例：`bench/case.json` + `bench/material/`（两篇文献，数据均虚构）。
- **baseline**：`bench/baseline/manuscript.md` —— 构造的「无证据链直写」模拟产物，
  复现文献中反复报告的基础 Agent 典型失败：越界强结论（已被证明/显著提升/领域共识）、
  数值失真（45%→98%、约 30% 无出处）、隐藏冲突证据（不提 Paper-B 阴性小样本结果）、
  引用 [1] 无可复核锚点。**它是构造基线，不是平台白板，也不是任何真实模型的输出。**
- **skill**：`bench/skill/` —— 证据绑定流程产物：证据库 + 论断-证据绑定矩阵 +
  内嵌编号成稿 + result.json，并经 `evidence_lib.py check`（rc=0）与
  `check_result.py`（rc=0）机检。

## 度量结果（确定性、可复算）

| 指标 | baseline | skill | 结论 |
|-|-|-|-|
| 数值锚定率（成稿数值可在材料原文找到） | 0.833 | **1.000** | skill 优 |
| 论断-证据绑定率（引用标记可解析到有绑定的论断） | 0.000 | **1.000** | skill 优 |
| 越界强度词数（硬词无 A 级证据支撑） | 4 | **0** | skill 优 |
| 冲突/阴性证据并陈 | 否 | **是** | skill 优 |
| 人工返工项（未锚定数值+越界词+未绑定引用+隐藏冲突） | 9 | **0** | skill 优 |
| 可独立复核产物数 | 1 | **4+** | skill 优 |

机检：`evidence_lib.py check` rc=0（报告落 `bench/skill/verification_report.json`）；
`check_result.py` rc=0。baseline 无可机检产物——「无法被机器复核」本身即是对照发现。

## 边界（诚实声明）

1. 本对照度量**证据支撑的结构与可核验性**（绑定率、锚定率、强度对齐、冲突并陈、
   返工项），**不度量 LLM 端到端写作质量**；后者由平台 harness 用固定案例对
   基础 Agent / 加载 Skill 的 Agent 给出，本 bench 不声称替代之。
2. baseline 为构造模拟，其失败类型取自题目「找得到/对得上/说得准/复得现」所列
   高频失败的典型形态；真实基础 Agent 的表现以平台对照为准。
3. 案例材料为自编虚构，仅演示度量口径；`bench_run.py` 可替换材料与产物后复用。
