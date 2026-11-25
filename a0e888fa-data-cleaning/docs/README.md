# 科研数据清洗与处理 v3.0.0

## 最小输入与交付

输入 `/input/case.json`、`/input/task.md`、实际 CSV/导出表和带版本的数据字典/workorder；输出 `/app/output/result.json`、清洗表、行级变更、质量报告、转换/复算日志。保留案例原 `output_contract`，示例不是正式案例答案。完整规则见根目录 `SKILL.md`，版本与增量边界见 `REVISION.md`。

## 命令（全部仅用 Python 标准库）

```bash
# 原画像/简单聚合复算/结构检查
python3 scripts/data_tool.py profile data.csv
python3 scripts/data_tool.py recheck result.json --csv data.csv
python3 scripts/data_tool.py schema result.json

# 字典→逐字段策略与 blocker
python3 scripts/cleaning_tool.py plan dictionary.json --csv data.csv > field_plan.json
# 跨表键归一、重复/冲突/未匹配审计
python3 scripts/cleaning_tool.py keys left.csv right.csv --left-key id --right-key sample_id > key_audit.json
# 原值保留 + Decimal 逆算 + 编码/单位审计
python3 scripts/cleaning_tool.py convert convert_plan.json --input data.csv --out cleaned.csv --audit conversion_audit.json
# result↔report↔cleaned 实算对账，版本/规则/真实 SHA-256 检查
python3 scripts/cleaning_tool.py audit result.json --cleaned cleaned.csv --report quality_report.json
```

已知旧编码时在 `convert` 加 `--source-encoding gbk --output-encoding utf-8`。所有 JSON 命令 0 表示通过、1 表示输入/质量/契约失败、2 表示用法错误。失败不代表可忽略；按 `unchecked/change_log` 记录。

`recheck` 仅覆盖原始 CSV 可直接表达的 count/sum/mean/min/max。清洗筛选、转换、连接、复杂公式需保存同快照复算代码和中间表。转换自动单位范围及统计/图表边界见 `SKILL.md`。

## 模板与维护

`templates/data_dictionary.md` 含机器可读字典、转换计划和质量报告骨架。修改规则/数值代码后运行：

```bash
python3 bench/bench_run.py   # 29/29
```

测试使用临时合成输入，覆盖正向零误杀和异常/篡改变异，不包含组织方正式测试答案，也不证明平台基础 Agent 对照增益。
