---
name: statistics-interpretation
description: 科研统计分析与结果解读。用于带缺失、异常、重复观测的数据表或 SQLite 导出；按独立/配对/单样本设计、样本量和分布自动选检验，交付描述统计、自由度、p值、效应量、95%区间、Holm校正和可复核结论。字段单位不明先追问，结论绑定同一效应量与区间。纯标准库。
---

# 统计分析与结果解读（v3.0.0）

**判对总闸：研究设计不匹配不算；缺失/异常/重复口径未记录不算；只有 p 值不算；效应量、区间或自由度缺失不算；结论与外部 `infer` 结果、效应方向、区间或 p 显著性不一致不算。** 不把统计显著写成实际重要或因果证明。不适用：实验设计/样本量估算、未支持的重复测量/协变量模型、因果推断及论文投稿。

## 1. 输入、输出与诚实降级

读取 `/input/case.json`、`/input/task.md`、实际表、字段字典和原 `output_contract`；以材料为事实，不能从 Concrete/Iris/Wine 等标签猜列义、样本来源或单位。Iris 等若材料声明特定来源变体须写入血缘。保留原字段与真实 `case_id`，`/app/output/result.json` 不得省略原输出字段。

先写 `status:"partial"` 的最小结果和 `unchecked`，逐步交付：清洗后分析行集、描述统计表、`analysis_result.json`、`result.json`、复算代码/SQL/日志、必要图表及数据表。材料缺失、无法判断和运行失败分别报告；未知不填 0。

工具为 Python 3 标准库：`data_tool.py` 负责画像/简单聚合复算/旧结构，`stats_tool.py` v3.0.0 负责自动选检验、数值推断与结论审计。数据库用只读 SQLite 查询后导出，保留 SQL、数据库版本/哈希和导出行数；不要把数据库运维当统计结果。

## 2. 可复跑流程

### 2.1 统计数据准备与字段口径

```bash
python3 scripts/data_tool.py profile data.csv
```

保留 `missing/duplicate_rows/outliers_iqr/dirty_numeric_count` 及行号。缺失不置 0；整行删除/成对删除/有效样本口径必须选择并报告每组排除数。异常值未经字段语义核查不自动删；完全重复不直接等于独立重复实验，先确认主键、配对/重复测量结构。字段字典至少给 `value` 的含义、单位、来源、缺失令牌，分组和配对字段的角色；单位/设计不明先提问，不硬算。

图表选择：单变量用直方图/ECDF 观察分布，分组用箱线或散点叠加显示样本量和异常点，配对用差值图并画 0 参考线；所有图存可编辑源数据，不能仅给美化图片。描述统计给 n、均值/SD、中位数/Q1/Q3、范围、偏度/超额峰度、缺失率及单位。

### 2.2 分析规格：先声明设计，再让工具选检验

`analysis_spec.json` 示例（**仅接口示意，不是正式案例答案**）：

```json
{"spec_version":"spec-v1","dictionary_version":"dict-v1","analysis_id":"A1",
 "design":"independent","value":"y","group":"arm","unit":"mg/L",
 "missing_tokens":["","NA","-999"],"max_missing_fraction":0.20,"alpha":0.05,
 "random_seed":20261125,"minimum_important_effect":0.2,"pairwise":false}
```

`design` 为 `independent/paired/one_sample`；paired 额外给 `pair`，one_sample 可给 `mu0`。`minimum_important_effect` 必须与所选效应量同口径且来自任务/领域阈值；没有就删除该键，工具返回 `not_assessed` 和人工问题，**不得从 p 值反推实际意义**。

```bash
python3 scripts/stats_tool.py recommend data.csv --spec analysis_spec.json > recommendation.json
python3 scripts/stats_tool.py infer data.csv --spec analysis_spec.json --out /app/output/analysis_result.json
```

自动选择规则及边界：

| 设计与数据 | 通过参数法筛查 | 未通过/小样本 |
|-|-|-|
| 独立两组 | Welch t（不强制等方差） | Mann–Whitney U + 秩双列相关 |
| 独立三组及以上 | 单因素 ANOVA + η²；追问的事后两两比较用 Holm | Kruskal–Wallis + ε²；事后比较用 Holm |
| 配对 | 对“每对差值”做 paired t + Hedges dz | Wilcoxon signed-rank + 配对秩双列相关 |
| 单样本 | 对 `x-mu0` 做 one-sample t + Hedges dz | Wilcoxon signed-rank |

参数法筛查显式保存每组 n、偏度、超额峰度及组内方差：n≥8、|偏度|≤1、|超额峰度|≤3、非零方差才作为默认参数法入口；多组 ANOVA 还检查组内方差比，明显不齐时降级秩检验。两组 Welch 不需要等方差，但仍报告各组 SD。**这是一种透明启发式分布筛查，不是 Shapiro–Wilk，也不是“证明正态”**；题目另给设计约束或公认方法时应优先并说明。组内/差值零方差切换秩法，不执行除零。

`infer` 输出描述统计、`test.name/statistic/df/p_value`、效应量及 95% CI、带单位的位置估计、样本排除、假设筛查和不确定性。非参数 p 值采用连续性/并列秩校正的正态近似；秩效应区间为正态近似，多组效应和中位数位置区间为固定种子组内/配对 bootstrap，实际次数与种子均写入输出。Wilcoxon/Mann–Whitney 不自动称为中位数检验。多组 `pairwise:true` 时同一 family 给 `p_adjusted_holm`，显著性看校正后 p。

### 2.3 把效应量与区间绑定到具体结论

`conclusion` 必须复制同一分析的 `analysis_id/effect_ref/ci_ref/effect_metric/effect_value/effect_ci`，并给 `statistically_significant` 与 `practical_importance`。标准表述：

> 在声明的分析行集与 α 下，是否达到统计阈值；给方向、效应量名称/数值/95% CI 和 p 值；与预设最小实际重要阈值比较，若无阈值则未评估；最后列设计、缺失、近似区间和外推限制。

“不显著”不等于“证明无效”；CI 不是个体取值范围；p 不是效应大小或结果重复概率。多组结论引用 Holm 校正结果，不用 omnibus p 替代具体两两方向。

### 2.4 独立复算与交付审计

```bash
python3 scripts/data_tool.py schema /app/output/result.json
python3 scripts/data_tool.py recheck /app/output/result.json --csv data.csv
python3 scripts/stats_tool.py audit /app/output/result.json --analysis /app/output/analysis_result.json
```

将 `analysis_result.json.analysis` **原样**放入 `result.json.statistics[]`，问题 evidence 用 `analysis:A1.test` 和 `analysis:A1.effect`。`audit` 对照外部推断文件，检查 p/df/效应量/区间、点估计落在区间内、结论显著性与 p 一致、问题—分析—效应—CI 绑定、Holm 字段，以及版本/血缘/真实文件 SHA-256。`recheck` 只覆盖它能表达的简单聚合；清洗筛选、配对和推断由保存的同快照代码及 `analysis_result.json` 复核。

## 3. 异常处置表

| 题面失败情形 | 识别与动作 | 输出 |
|-|-|-|
| 样本量不足 | 每组/完整配对有效 n<3，`SAMPLE_TOO_SMALL` 阻断推断 | 仅描述统计、`partial/issues`、需补数据 |
| 组内/配对差方差为零 | 不执行 t/ANOVA 除零；切换秩检验；全零差 p=1、效应 0 | warning、所选方法、有限区间 |
| 缺失比例过高 | 默认任一组 >20% 即 `HIGH_MISSING`，阈值可由规格预先调整；不填 0 | 各组缺失数/分数、缺失机制问题、敏感性需求 |
| 非数值/统计假设不成立 | 脏数值先阻断；小样本/偏态/零方差/多组方差明显不齐改非参数 | `DIRTY_NUMERIC` 或 `distribution_screen` 及改法理由 |
| 字段单位或设计不明 | `UNIT_UNKNOWN`/规格字段缺失，返回 `questions`，不生成推断数字 | `partial`、待确认单位/换算/配对结构 |
| 重复记录/配对冲突 | 重复行只标记不静默删；同一 pair×group 多条是 `PAIR_CONFLICT` | 原行号、真实主键确认、排除表 |
| 异常值影响结论 | IQR 只标记；保留含/不含异常的同口径敏感性分析，不能挑显著的一版 | 行定位、两版行集与差异、不确定性 |
| 多重比较未校正 | 多组指定 pairwise 必须 Holm；`audit` 对缺失校正值报错 | family_size、raw p、adjusted p |
| 数据库连接失败/权限不足 | 保存驱动/只读连接与 SQL 错误；用合法导出重试，失败则不猜字段/数值 | `partial/failed`、失败 SQL/错误、已核实行数 |
| 输入损坏/空表 | 严格 UTF/GB18030 解码、NUL/CSV 结构检查；空表不推断 | 文件/行定位、`partial/failed` |

## 4. result.json 可核验契约（字段示意，数字须来自实际运行）

```json
{
 "case_id":"实际case_id","status":"pass",
 "questions":[{"id":"Q1","answer":"实际解释","evidence":["analysis:A1.test","analysis:A1.effect"]}],
 "statistics":[{"analysis_id":"A1","test":{"name":"welch_t","statistic":0,"df":0,"p_value":1},
   "effect":{"name":"hedges_g","value":0,"ci":[0,0],"direction":"A-B"},
   "estimate":{"name":"mean_difference","value":0,"unit":"实际单位","ci":[0,0]},
   "conclusion":{"analysis_id":"A1","effect_ref":"A1.effect","ci_ref":"A1.effect.ci","effect_metric":"hedges_g","effect_value":0,"effect_ci":[0,0],
     "statistically_significant":false,"practical_importance":{"label":"not_assessed"}}}],
 "aggregates":[{"column":"y","op":"count","value":0,"group_by":"arm"}],
 "data_dictionary":{"y":{"semantic":"实际含义","unit":"实际单位","source":"dictionary.fields.y"}},
 "lineage":{"snapshot":"实际快照ID","tables":["data.csv"],"filters":[],"join_keys":[],
   "inputs":[{"path":"/input/data.csv","sha256":"实际64位SHA256"}]},
 "run":{"skill_version":"3.0.0","tool_version":"3.0.0","ruleset_version":"stats-rules-v1","dictionary_version":"dict-v1",
   "python_version":"实际platform.python_version()","started_at":"实际UTC时间","random_seed":20261125},
 "gain":{"baseline_accuracy":null,"skill_accuracy":null,"rework_rounds_saved":null},
 "quality":{"rows_input":0,"duplicate_rows":0,"missing_by_group":{},"iqr_outliers_by_group":{}},
 "artifacts":[{"path":"/app/output/analysis_result.json","sha256":"实际64位SHA256","type":"analysis"}],
 "unchecked":[],"sources":["/input/data.csv"],"uncertainty":[],"change_log":[]
}
```

`statistics` 必须含 `infer` 完整对象，而非只复制片段；所有版本/时间/种子来自实际运行。无同输入同权限的基础 Agent 原始对照时 `gain=null`，不能编造提升或 benchmark 分数。

## 5. 最小调用、自测与增量边界

合成 CSV 加 `analysis_spec.json` 后运行 `profile → recommend → infer → schema/recheck → audit`；无跨表数据时 `recheck` 只声明确实存在的简单聚合。维护或验收运行：

```bash
python3 bench/bench_run.py   # 当前 34/34；正向零误杀 + 样本/缺失/单位/零方差/假设/结论/CI/Holm/版本/哈希变异
```

边界：支持连续结局的独立、配对和单样本常见比较；不自动处理分类结局、回归协变量、重复测量混合模型或精确小样本秩 p 值。p/区间方法均带近似或 bootstrap 标签，用户不能把启发式选择当领域裁决。相对基础 Agent 的增量边界是**设计/分布选择可执行、效应—区间—结论机检绑定、口径不明主动阻断**；不声称未经平台公平对照的质量提升。
