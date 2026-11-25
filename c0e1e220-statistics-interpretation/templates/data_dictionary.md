# 字段字典、统计规格与复算模板（v3）

以下为**可编辑模板/合成示例**，不是正式案例答案。字段名称、单位、研究设计、最小实际重要阈值只能来自实际材料和任务；不确定时保留 blocker/question。

## 1. 字段字典

| 字段 | 含义 | 角色 | 单位 | 缺失令牌 | 来源定位 |
|-|-|-|-|-|-|
| y | 连续结局 | measurement | 实际单位 | 空串、NA、-999 | dictionary.fields.y |
| arm | 分组 | categorical | — | 空串 | dictionary.fields.arm |
| subject_id | 配对/受试者标识 | identifier | — | 空串 | dictionary.fields.subject_id |

- 数字编码的分类/标识字段不当连续变量；日期/重复测量结构先确认。
- 缺失不置 0。完全重复不自动等于错误记录；同一 pair×group 多条是配对冲突。
- 数据库来源附 SQL、SQLite/数据快照版本、数据库与导出 CSV 哈希、查询行数。

## 2. `analysis_spec.json`

### 独立两组/多组

```json
{
  "spec_version": "spec-v1",
  "dictionary_version": "dict-v1",
  "analysis_id": "A1",
  "design": "independent",
  "value": "y",
  "group": "arm",
  "unit": "实际单位",
  "missing_tokens": ["", "NA", "-999"],
  "max_missing_fraction": 0.20,
  "alpha": 0.05,
  "random_seed": 20261125,
  "minimum_important_effect": 0.2,
  "pairwise": false
}
```

`pairwise:true` 用于三组及以上的预先声明两两比较 family；Holm 自动校正。`minimum_important_effect:0.2` 仅是输入格式示意；没有同口径领域阈值时删除该键，结果给 `not_assessed`。

### 配对设计

沿用上述字段，改为 `"design":"paired"` 并增加 `"pair":"subject_id"`。`arm` 恰有两水平，每个 pair×arm 最多一行；工具分析每一对 `first-second`，方向在输出中记录。

### 单样本设计

改为 `"design":"one_sample"`，删除 `group/pair`，增加 `"mu0":0`。工具对 `x-mu0` 分析；mu0 必须来自问题而非为了显著而调整。

## 3. 选择与方法记录

```bash
python3 scripts/stats_tool.py recommend data.csv --spec analysis_spec.json > recommendation.json
python3 scripts/stats_tool.py infer data.csv --spec analysis_spec.json --out analysis_result.json
```

- 独立两组：Welch t 或 Mann–Whitney；Welch 不要求等方差。
- 独立多组：ANOVA 或 Kruskal–Wallis；ANOVA 还查最大/最小组内方差比。
- 配对/单样本：差值 paired/one-sample t 或 Wilcoxon。
- 参数法入口默认 n≥8、|偏度|≤1、|超额峰度|≤3、非零方差；这是透明启发式筛查，不是正态性证明。高缺失/口径不明先阻断，不用换方法“凑显著”。
- p 值含并列秩和连续性校正标记；非参数近似/bootstrap 不可改称精确法。

## 4. 结论与 evidence

将 `analysis_result.json.analysis` 原样放进 `result.statistics[]`，不要手改 p、效应或 CI。每个主观问题引用：

```json
{"id":"Q1","answer":"按实际结果撰写","evidence":["analysis:A1.test","analysis:A1.effect"]}
```

结论至少回答：设计/有效 n、检验与 df/p、方向、效应量/95% CI、统计阈值、实际重要性阈值或未评估、排除与假设限制。多组具体方向引用 Holm 校正 p，不用 omnibus p 替代。

## 5. 交付前清单

- [ ] 数据字典、设计、单位、缺失令牌和分析 ID 均有版本/来源。
- [ ] 描述统计含 n、中心/离散/分位数、分布形态、缺失与异常/重复口径及单位。
- [ ] 配对结构或独立结构真实，异常/重复排除可回到行号。
- [ ] `recommend/infer` 完成，检验有统计量、df（适用时）、p，效应量与区间完整。
- [ ] 多组预声明 family 有 Holm；无实际重要阈值时不编造。
- [ ] 结论与同一分析的效应、方向、CI 和 p 一致；非显著不写成证明无效。
- [ ] `schema/recheck/audit` 全通过；复杂筛选/配对另存同快照代码和中间表。
- [ ] `run` 版本/UTC/seed、输入和产物真实 SHA-256、SQLite SQL/日志（如有）齐全。
- [ ] `python3 bench/bench_run.py` 34/34；不把本地 bench 当平台对照增益。
