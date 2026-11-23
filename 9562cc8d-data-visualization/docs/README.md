# 科研数据可视化

## 用途
本题聚焦**数据可视化**：图型要与数据类型和目的匹配（分布/比较/相关/趋势/构成），编码方式不夸大差异（面积、角度、双轴），坐标轴单位与误差线定义明确。图下数据必须与 `aggregates` 一致，不得图上一套数、表里另一套。

## 调用
输入 `/input/case.json` 与 `/input/task.md`；输出 `/app/output/result.json` + 产物。

## 命令
```bash
python3 scripts/data_tool.py  # 见下
```
`profile data.csv`（缺失/重复/异常值/量级不一致/脏数值）/ `recheck result.json --csv data.csv`（重算并比对）/ `schema result.json`

## 模板
`templates/data_dictionary.md`

## 自测
```bash
python3 bench/bench_run.py   # 10/10
```

## 适用边界
处理给定材料；不声称在线全覆盖；模型判定为待人工确认的建议。
