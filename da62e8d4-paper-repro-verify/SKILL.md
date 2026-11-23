---
name: paper-repro-verify
description: 论文复现与方法验证 Skill。面向"参数/代码/指标验算与差异归因"：参数三分类抽取、口径卡强制校验、运行候选数值方法、事前容差与多种子统计对照、"数值等级×证据等级"二维判定、8 类偏差归因、缺失参数敏感性扫描。产出 /app/output/result.json 与可复核报告。触发词：论文复现、方法验证、指标核对、参数复原、容差对照、差异归因、敏感性扫描。
---

# paper-repro-verify：论文复现与方法验证（v2）

## 0. 适用边界（来自题面"本版明确任务范围"）
- 本子场景是"参数/代码/指标验算与差异归因"：实际运行案例包内的**两份候选数值方法**，核对**原始来源、实际环境、事前容差**。
- 组织方合成试验**不是**原作者代码、物理实验或全量 PMLB 复现；案例明确保留缺失的原始数据/仓库时，**不得补造**，登记为"无法验证（材料不足）"。
- 只使用 Python 标准库（numpy/matplotlib 可用时才用）；**禁止 pip、禁止联网拉代码**。

## 1. 预算纪律（硬性，违者判 0）
- 每案例模型请求 **≤12 次**，全程 **≤600 秒**，单次响应含推理 ≤16384 tokens。
- **先写诚实结果再改进**：进入案例后第 3 次请求内必须已写出 `/app/output/result.json` 骨架（status=partial），之后每完成一个环节回写一次。
- 数值计算、表格生成、对照、统计一律交给 `scripts/reprokit.py`，不在对话里手算长数字。

## 2. 输入与输出契约
- 输入：`/input/case.json`（含 `case_id` 与 `output_contract` 字段清单）、`/input/task.md`、案例材料（PDF/代码/数据，以实际文件为准，不凭标签臆测）。
- 工作区：`/app/work`；交付：`/app/output/`。
- 必交付：
  - `result.json`：含 `output_contract` 全部字段 + `case_id` + `status`（success/partial/failed + 原因）+ `sources` + `uncertainty` + `missing_materials` + `change_log`。用 `init` 生成骨架。
  - `repro_report.md`：复现清单→环境快照→参数表→口径卡→运行记录→敏感性/多种子统计→二维对照→8 类归因→分级结论。

## 3. 七步工作流（每步≤2 次模型请求）
1. **材料定位**：读 case.json/task.md/材料清单，建复现清单（代码、数据、参数、依赖、许可证逐项标注来源/版本/缺失）；缺失项登记 `missing_materials`。
2. **环境快照**：`reprokit.py env --out /app/work/env.json`，与论文/案例环境逐项比对记录不一致。
3. **参数复原**：抽取关键参数写 `params.json`（schema 见 §5），分 `paper`/`code`/`self`；冲突项在 notes 说明取舍，`params --table ...` 校验；有 self 参数时用 `sensitivity` 扫描量化影响。
4. **口径卡强制校验**：每个对照指标建口径卡（定义/数据划分/聚合方式/精度/定位），`card --spec card.json`；不一致**先纠正再比数值**，不得事后归因。
5. **事前声明容差与证据等级**：运行前写定容差（优先取 task.md；否则默认相对 2%、定性带×5，注明自定）与证据等级（T1 仅文本/T2 公开数据/T3 公开代码或独立重实现/T4 代码+数据+固化环境）。**不允许先看结果再定容差。**
6. **代码运行**：按参数表运行两份候选方法，固定并记录种子、命令、耗时、原始输出到 `/app/work/runs/`；失败也记录。含随机性的方法按 **≥5 个种子** 重复（§5 统计协议）。
7. **结果比较与归因**：`compare`（二维判定）+ `stats`（多种子 CI）+ `attribution`（8 类归因）→ 给 可复现/部分复现/不可复现 结论，回写 result.json 与 repro_report.md。

## 4. 判定口径（v2 二维矩阵）
- **数值等级**：`复现一致`（|相对误差|≤事前容差）／`定性一致`（超容差但在定性带内，或趋势/排序/符号一致）／`不一致`（超定性带或方向相反）／`无法验证（材料不足）`（原文未给数值或缺少运行材料）。paper=0 时按 `abs_tolerance` 绝对容差判定。
- **证据等级**：T1 仅文本 / T2 公开数据 / T3 公开代码（或独立重实现+固定种子）/ T4 代码+数据+固化环境。
- **二维结论**：`"{数值等级} × {证据等级}"`，如 `复现一致 × T3`。单一数值等级不得掩盖证据强弱；声称"复现一致"须同时声明证据等级。

## 5. schema 与子命令
- `params.json`：`{"parameters":[{"name":"n_grid","method":"A","value":100,"source_class":"paper","location":"§3.1","notes":""}]}`。
- `card.json`（口径卡，对照前强制校验）：`{"metrics":[{"metric":"I","paper":{"definition":..,"data_split":..,"aggregation":..,"precision":..,"location":..},"repro":{..}}]}`；默认 check_fields=definition/data_split/aggregation/precision。
- `spec.json`（compare 输入）：`{"default_tolerance":0.02,"qualitative_factor":5,"abs_tolerance":null,"default_evidence_grade":"T3","tolerance_basis":"..","metrics":[{.. paper/repro/tolerance/abs_tolerance/evidence_grade/location}]}`。paper/repro 为 null → 数值等级"无法验证"。
- `runs.json`（stats 输入）：`{"paper":{"I":0.4597},"metrics":[{"metric":"I","method":"A","values":[..≥5 个种子值..]}]}`；输出 mean/std/sem/ci95 + `paper_in_ci`。
- `grid.json`（sensitivity 输入）：`{"func":"evaluate","baseline":{..},"params":[{"name":"n_grid","values":[50,100,200]}],"metrics":[..],"tolerance":0.02}`；方法文件提供 `evaluate(**params)->dict`。
- `attribution.json`（8 类归因单）：`{"attribution":[{"metric":"I","method":"A","cause":"实现差异","evidence":"code L12"}]}`。

## 6. 8 类偏差归因（每条必须附 evidence）
枚举（与 failure mode 一一对应）：`环境/依赖漂移`、`随机性/种子`、`参数缺失或漏抽`、`口径不一致`、`原文笔误（疑似）`、`实现差异`、`统计波动`、`无法判定`。
证据来源：环境/依赖漂移→env.json 对比；随机性/种子→多种子 CI；参数缺失或漏抽→敏感性排序；口径不一致→口径卡 mismatch；原文笔误（疑似）→两处原文对照；实现差异→候选方法代码行号；统计波动→CI 宽度；无法判定→材料不足。

## 7. 异常处理
- 材料不足以复现：不猜数，verdict=无法验证，`missing_materials` 逐条列（什么材料、缺它导致哪步做不了、人工接管入口）。
- 脚本/方法运行失败：记录 stderr 摘要与失败步骤，status=partial，已完成环节照常交付。
- 材料内部冲突（正文 vs 附录 vs 代码默认）：三处都引，采用优先级 任务声明 > 论文明示 > 代码默认，并记录取舍。
- 口径卡不一致：阻断数值比较，先纠正口径；敏感性/统计结果不得替代口径一致。
- 任何情况下**不伪造**运行结果、环境状态或论文数值。

## 8. 最小调用示例（自拟材料，仅演示接口，非正式案例结果）
见 `examples/minimal_case.md`：自编"论文"短材料 + 两个候选数值积分方法，演示 env→params→card→compare（二维）→stats（多种子）→sensitivity→attribution→判定的完整调用与示意输出（已标注"示例"，数值已实跑核对）。

## 9. 包内文件
- `SKILL.md`：本说明。
- `scripts/reprokit.py`：env / params / card / compare / stats / sensitivity / attribution / init 八个子命令，仅标准库。
- `templates/result.template.json`：result.json 骨架样例（含口径卡/二维对照/统计/敏感性/归因字段）。
- `examples/minimal_case.md`：最小调用示例（标注示例）。

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
