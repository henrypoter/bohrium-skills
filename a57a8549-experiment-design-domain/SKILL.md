---
name: experiment-design-domain
description: 实验方案设计总课题路由：以原文证据分诊生成、比较、可行性、参数、结果解释，并调用可执行的比较/资源/有限域优化/残差接口统一复核。
---

# 实验方案设计领域总课题（先分诊，后执行）

## 触发与适用边界

用于实验方案生成与优化、多方案比较、可行性审查、参数优化、结果解释与异常分析。先读取真实 `/input/task.md`、`/input/case.json` 及随案材料，**不得跳过路由直接套通用方案**。纯标准库，无安装/网络依赖。

不代替安全/伦理批准，不执行实验，不把代理模型结果冒充实测，不凭残差给因果结论。未知任务返回 `unsupported`；数据缺失写 `not_checked`，工具/权限失败写 `failed/partial`，不得默认“满足”。

## 任务分诊表（机器可执行）

| 子任务 route | 强触发信号（示例） | 对应 workflow / 命令 | 必备交付与机检 |
|-|-|-|-|
| `generation` 生成与优化 | 设计实验、生成/制定/提出方案、design experiment | `generate_check`；`audit` | hypothesis、变量操作定义、对照混杂、步骤、参数、资源、风险三件套 |
| `comparison` 比较与选择 | 比较候选方案、多方案、方案选择/取舍、compare/rank | `compare_then_select`；`compare + audit` | 同口径指标、归一化权重分、硬拒绝、版本化候选、逐项权重敏感性 |
| `feasibility` 可行性 | 可行性、资源核验、能否实施、设备可用、伦理审批 | `versioned_feasibility_review`；`resources + params + audit + verify` | 七类检查、四态资源、样本/预算/排期算术、量程交集、条件清单 |
| `parameter` 参数优化 | 参数优化/取值/建议、搜索策略、可行域 | `bounded_parameter_optimization`；`optimize + replay + params + audit` | 响应测量/不确定度、有限域穷举、三成本、Pareto、完整重放、停止依据 |
| `interpretation` 结果解释 | 结果解释、异常结果/分析、趋势、残差、归因、interpret | `result_residual_analysis`；`interpret + audit + verify` | 拟合系数、逐点残差、MAD阈值、异常ID、独立复核动作、非因果声明 |

先运行：

```bash
S=/skills/weekly-skill/scripts/exp_tool.py
python3 "$S" route --task /input/task.md --case /input/case.json --out /app/work/routing.json
```

`routing.json` 带 `route_schema_version`、task/case SHA-256、每个 route 的行号或 JSON Pointer、逐字 quote、workflow、所需命令及输出。显式 `case.task_type` 优先提供高权重字段证据。可返回多个路由，主路由按匹配证据数及固定优先级确定，**所有已触发子任务都必须执行**，不能只完成 primary。五类均无命中时返回 1、`primary=unsupported`、交用户澄清，禁止默认为 generation。

## 共同底座

1. 将 research goal 落成可证伪 hypothesis；变量含 `type/operational_definition/unit/range`，对照含 `confounder_excluded`。
2. 步骤绑定实际设备、材料、参数和资源；风险必须有 `trigger/mitigation/stop_rule`。
3. 源材料登记 `sources[]={source_id,version,path,sha256}`；判断/参数/响应/路由证据均为 `{source_id,location,quote,sha256}`。JSON 值须与 pointer 完全一致，文本 quote 须为逐字子串；PDF 用真实提取文本和页码，无法读取的页标 not_checked。
4. `result.json` 保留原 output_contract，并固定 `result_schema_version=integrated-result-3.0.0`、`tool_version=integrated-exp-tool-3.0.0`、`plan_version`、实际输入/权限哈希。
5. 任何未覆盖任务要求的对象写 `unchecked`，任何推断、代理模型、假设写 `uncertainty`，需专家决定事项写 `expert_confirmation`，方案变更写 `change_log`。

最终统一检查：

```bash
R=/app/output/result.json
python3 "$S" audit "$R"
python3 "$S" verify "$R" --source-root /app/work/source_snapshot
python3 "$S" schema "$R"
# 路由触发时再运行对应 resources/optimize/replay/params/compare/interpret
```

## 分流流程 A：生成与优化

依次完成目标→变量→对照→步骤→设备材料→参数→成本→风险；`audit` 对该路由强制 hypothesis、steps、parameters。参数不是“看起来合理”：有限数值限值放 problem/limits，`params` 计算 `max(min)`/`min(max)` 并核对步进、单位、derived_min/max。

```bash
python3 "$S" params "$R" --spec /app/work/problem.json
```

## 分流流程 B：方案比较与选择

比较输入含至少两个不同 `id/plan_version` 的候选和一致 metrics。每项指标给 `direction/weight`，可给硬 min/max；缺指标或 NaN 直接拒绝。

```bash
python3 "$S" compare /app/work/comparison_input.json --out /app/work/comparison.json
```

- 先执行硬阈值，不能靠高总分掩盖安全/预算不合格。
- 合格候选按指标方向 min-max 归一化，常数指标 desirability=1，正权重归一化求 score；同分按 id 稳定排序。
- 对每项权重做 ±`sensitivity.weight_delta` 的单因素扰动（负权重截为0），列出 top 是否稳定。
- 输出所有 rejected 及理由、rejected 后的推荐和 sensitivity。比较版本/权重改变必须重跑；最终 comparison 嵌入 result。

## 分流流程 C：可行性与资源

七类检查为假设变量、对照、设备材料、时间成本、参数范围、风险异常、伦理安全，每类恰好一次并有定位/证据；not_checked 填 reason，conditional 和“有条件可行”填可验收条件。

```bash
python3 "$S" resources "$R"
python3 "$S" params "$R" --spec /app/work/limits.json
python3 "$S" verify "$R" --source-root /app/work/source_snapshot
```

设备/材料状态为 `available/outsource/purchase/unavailable/not_checked`；available 设备必须有型号、精度、单位、附件和清单行。成本逐行乘法、总额求和；样本缺口实算。单步工时=`max(设备,人工)+等待+周转`，同并行组取最长，采购最长货期前置，再求组间总和。pending/not_checked 伦理安全审批必须给 action 并停止放行。

该路由额外强制十类异常：方案缺页、参数缺失、设备不明、伦理未定、自相矛盾、超长文档、设备故障、材料批次差异、样本不足、参数越界。每条给 signal/action/disposition/owner/linked_fields。

## 分流流程 D：有限域参数优化

problem 必须来自真实约束与模型，结构、完整公式和样例见 `templates/plan_spec.md` 及 `bench/fixtures/problem.json`。

```bash
python3 "$S" optimize /app/work/problem.json --out /app/work/optimization.json
# 完整 optimization 嵌入 result 后：
python3 "$S" replay /app/work/problem.json "$R"
python3 "$S" params "$R" --spec /app/work/problem.json
```

工具只支持有限网格、显式线性响应/成本/组合约束。完整枚举每点后过滤量程、步进、响应阈值与机时/费用/样本预算；可行集内计算归一化效用及全响应+三成本 Pareto。grid 超 max_evaluations 拒绝，不静默截断；无可行解 recommended=null 且保留全部拒绝码。`replay` 重算整个对象，防篡改轨迹/推荐。

响应必须写 measurement_method、unit、direction、acceptable_variation 和 uncertainty；search 与 stopping_reason 一致，成本字段与推荐候选一致。连续/高维/非线性/贝叶斯优化声明不适用并转专用流程。

## 分流流程 E：结果解释与异常分析

```bash
python3 "$S" interpret /app/work/observations.json --out /app/work/interpretation.json
```

输入为版本化 `{observations:[{id,x,y}],unit,absolute_residual_threshold}`；至少两个不同 x，有限数值。工具用最小二乘得到 intercept/slope/R²，输出逐点 observed/predicted/residual，计算残差绝对值中位数 MAD。异常阈值=`max(声明绝对阈值,2*MAD)`，严格 `|residual|>threshold` 才标 ID；完美线性且残差全0不误报。

解释结果只标 `descriptive_linear_fit_not_causal`，异常动作是核对原始记录/仪器并独立重测，**不自动删除异常点、不把相关写成机理**。复杂重复测量、非线性趋势、混杂归因须专用统计或专家复核。最终 interpretation 嵌入 result，异常证据回链源数据。

## 异常处置总表（每个结果都强制）

| code / 题面失败情形 | 识别信号 | 动作与绑定 |
|-|-|-|
| `unsupported_input` 不支持输入 | 五类无匹配或格式不可解析 | primary=unsupported，停止并交任务提交人；绑定 routing/status |
| `tool_error` 工具异常 | 非零退出且 error 存在 | 保留产物/错误码，受影响项 not_checked 并降级；绑定 status/unchecked |
| `permission_denied` 权限问题 | 源文件/设备 permission denied | 停止越权访问，保留权限哈希，交管理员；绑定 permissions_digest/status |
| `missing_data` 数据缺失 | 当前路由必填字段缺失 | 明确 not_checked，不默认满足；绑定 unchecked 和具体流程字段 |
| `execution_failed` 执行失败 | 算术/模型/写盘未完成 | status=failed/partial，保存已有审计记录并降级；绑定 status/change_log |

路由附加异常按上表加入同一 `exception_register`，每条仅一次且有 signal/action/disposition/owner/linked_fields。参数/解释还要求指标矛盾，参数另含无可行解、约束冲突、设备错误和权限不足；不要只写“注意”。

## 基础 Agent vs 本 Skill 公平对照

无平台基线时 `gain.status=not_run+reason`，不填估计分数。有真实同权限结果：

```bash
python3 "$S" gain /app/work/baseline_result.json "$R" --out /app/output/result_with_gain.json
```

强制相同 `case_id/input_digest/permissions_digest`，相同路由口径统计所需交付段、路由专属输出、定位判断、异常覆盖。仅双方同口径 telemetry 存在时记录 runtime/返工轮次；否则 `not_measured`。单次 pair 为 repetitions=1，三次重复保留三份独立原生记录。

## result.json 骨架、示例与自检

```json
{
 "case_id":"","status":"partial","plan_version":"v1",
 "result_schema_version":"integrated-result-3.0.0","tool_version":"integrated-exp-tool-3.0.0",
 "input_digest":"64-hex","permissions_digest":"64-hex","routing":{},
 "research_goal":{},"variables":[],"controls":[],"steps":[],"resources":{},"parameters":[],
 "risks":[],"judgments":[],"expert_confirmation":[],"unchecked":[],"sources":[],"uncertainty":[],"change_log":[],
 "exception_register":[],
 "gain":{"status":"not_run","reason":"","design":{"same_case_id":"","same_input_digest":"","same_permissions":true,"repetitions":1},"quality":{},"efficiency":{}}
}
```

按路由增加 `comparison/feasibility/response_metrics/search/cost_budget/optimization/interpretation`；`audit` 只强制当前路由必需项。合成最小示例在 `bench/fixtures`，不是正式测试答案。

```bash
python3 /skills/weekly-skill/bench/bench_run.py
```

bench 对五类路由无 extra-route、混合任务、不支持输入，以及所有命令的正向和变异均做测试。bench 通过证明接口/算术行为，不证明正式科研事实正确或优于榜首。
