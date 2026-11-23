# 最小调用示例（示例，非正式案例结果）

输入：同目录 example_input.csv（自拟脏数据）。调用：
```
python3 scripts/clean_tabular.py --input examples/example_input.csv --outdir /app/output --case /input/case.json --answers /app/work/answers.json
```
- cleaned_table.csv：R05 `572,F→300.0,°C`(U14)；R09 `50,nm→5e-08,m`(U07+prefix)；R04/R10 `NR→not_reported` 留空；R08 125 % 标 out_of_range；R11 `BTU lb-1` 未知单位 → 原值保留。
- change_log.csv：`R05,value/unit,572 F,300.0 °C,U14,std = raw * 0.555556 + (-17.7778)`；`R02,substance,anatase TiO2,TiO2,S01,同义名归一（待确认口径）`。
- anomaly_report.json：duplicates=[R01,R02]（同键换算后等值待确认合并）；possible_replicates=[R07,R08]（同键取值不同全部保留）。
- result.json：status=partial，sources 为全部 source_ref，uncertainty=needs_review 清单。
