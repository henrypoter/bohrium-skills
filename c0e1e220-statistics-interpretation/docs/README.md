# 统计分析与结果解读 v3.0.0

## 最小输入与交付

输入 `/input/case.json`、`/input/task.md`、数据字典、实际 CSV/SQLite 导出及分析规格；输出 `/app/output/result.json`、`analysis_result.json`、描述统计、清洗/排除记录、复算代码及任务要求的图表。保留原 `output_contract` 和 `case_id`。完整流程、异常表和方法边界见 `SKILL.md`。

## 命令（全部仅用 Python 标准库）

```bash
python3 scripts/data_tool.py profile data.csv
python3 scripts/data_tool.py recheck result.json --csv data.csv
python3 scripts/data_tool.py schema result.json

# 按设计、有效 n、分布和方差诊断选方法；不一致口径给 blocker/question
python3 scripts/stats_tool.py recommend data.csv --spec analysis_spec.json > recommendation.json
# 描述统计 + 检验/df/p + 效应量/CI + 结论 + 可选 Holm
python3 scripts/stats_tool.py infer data.csv --spec analysis_spec.json --out analysis_result.json
# result.statistics 原样对照外部 infer，检查结论/效应/CI/p/Holm/版本/真实哈希
python3 scripts/stats_tool.py audit result.json --analysis analysis_result.json
```

支持 independent/paired/one_sample 的连续结局：Welch t/Mann–Whitney、单因素 ANOVA/Kruskal–Wallis、paired/one-sample t/Wilcoxon。`pairwise:true` 对多组两两比较执行 Holm；`minimum_important_effect` 应与效应量同口径，没有阈值就未评估实际重要性。

正态性为透明启发式筛查，不是 Shapiro–Wilk；非参数 p/秩效应区间含近似，多组效应与位置区间用固定种子 bootstrap。复杂重复测量、分类结局、协变量模型应明确降级，不套用本工具。`recheck` 不替代配对/检验复算。

## 模板与维护

`templates/data_dictionary.md` 提供字段字典和分析规格骨架。修改选择逻辑、分布函数或审计规则后运行：

```bash
python3 bench/bench_run.py   # 34/34
```

测试含原命令回归、Welch 独立公式复算、正向零误杀及样本/缺失/单位/假设/结论/CI/Holm/SHA-256 变异；不包含正式案例答案或虚构平台增益。
