# 修订说明（v2 → v3.0.0，2026-11-25）

## 逐条对齐“是否做对”与评分维度

- **数据可统计、方法匹配设计**：原 `profile/recheck/schema` 保留；新增 `stats_tool.py recommend` 按独立/配对/单样本设计、有效 n、偏度、超额峰度、零方差选择 Welch t/Mann–Whitney、ANOVA/Kruskal–Wallis、paired t/Wilcoxon。多组 ANOVA 另有方差比筛查，Welch 不误加等方差要求。
- **数值、自由度和区间完整**：`infer` 纯标准库实现不完全 Beta/正则 Gamma 分布函数、Welch 自由度、t/F/卡方 p 值、并列秩与连续性校正；输出描述统计、检验统计量、df、p、效应量、95% CI、带单位位置估计与排除记录。
- **解释而非 p 值堆砌**：每个 `conclusion` 绑定 `analysis_id/effect_ref/ci_ref/effect_value/effect_ci`、统计显著性与同口径最小实际重要阈值；无阈值返回 `not_assessed`，不把 p=0.04 写成证明有效。
- **可复跑**：`analysis_result.json` 保留输入哈希、规格/字典版本、分布筛查、随机种子和实际 bootstrap 次数；`audit` 与 `result.statistics` 原样对账，并检查真实输入/产物 SHA-256。

## 创新增益（15）：三个自评缺口均变为机器能力

1. **按分布与设计自动选检验**：`recommend data.csv --spec analysis_spec.json`；参数法使用透明启发式入口，小样本/偏态/零方差/多组方差明显不齐降级秩法，绝不声称低功效正态检验“证明正态”。
2. **效应量与区间绑定结论**：`infer` 输出 Hedges g/dz、秩双列、η²/ε²及相应区间；Welch/t 位置区间、近似秩效应区间和固定种子 bootstrap 均标方法。`audit` 抓出结果手改、CI 不含点估计、p 与显著性表述矛盾、问题未引用分析。
3. **口径不明主动追问**：规格缺 `unit/design/value/spec_version/dictionary_version/analysis_id` 或单位为 `?` 时返回 blocker 和 `questions`，不产生貌似精确的统计数字。高缺失、脏数值、配对冲突亦然。

**相对基础 Agent/通用统计脚本的边界**：基础 Agent 也可能算出一个 p 值；本版固定了“设计—数据—假设—方法—效应—CI—解释”的机检链和阻断返回码。未宣称自测等同真实基础 Agent 对照增益。

## 可靠体验（10）与多重比较

异常表覆盖样本量不足、组内/差值零方差、缺失比例过高、统计假设不成立、字段单位不明、数据库连接失败，以及异常/重复/配对冲突、输入损坏。全零配对差安全返回 p=1、效应 0；恒定非零差不执行除零。多组指定两两比较时输出全 family 的 Holm 调整 p，`audit` 强制校正字段存在。

## 可核验字段与实际效果（40）

`result.json` 新约要求 `statistics[]`（完整 infer 对象）、`run`（skill/tool/ruleset/dictionary/Python 版本、UTC 时间、种子）、`lineage.inputs[]={path,sha256}`、`quality`、`artifacts[]={path,sha256,type}`，并保留原案例字段及 `case_id/status/questions/aggregates/data_dictionary/gain/unchecked/sources/uncertainty/change_log`。数据库来源须保存 SQL、版本、哈希与导出行数。

## Bench 证据（本地合成金标准，不是平台成绩）

```text
python3 bench/bench_run.py
34/34 PASS
```

原 10 项回归全保留。Welch 均值差和 t 由测试独立公式复算；正向覆盖参数法、非参数、恒定差/全零差、多组效应区间与 Holm、合规审计。变异覆盖样本不足、高缺失、未知单位、脏数值、多组方差不齐、结论脱离效应、显著性冲突、CI 不含点估计、版本/校正/SHA-256 缺失或造假，均有失败返回码。

## 生态与剩余限制

更新 `SKILL.md`、`docs/README.md`、`templates/data_dictionary.md`，补齐规格模板、方法边界、失败表和最小调用。当前不支持分类结局、协变量回归、复杂重复测量/混合模型；正态性为启发式筛查，非参数 p/部分效应区间是正态近似，多组/位置区间为 bootstrap，不冒充精确推断。平台三案例三次重复、基础 Agent 同条件原始输出、数据库真实失败恢复和大样本性能/图表复核仍是与榜首比较时缺少的外部证据。
