# 统计分析与结果解读

## 用途
本题聚焦**统计分析与解读**：检验选择与数据分布/设计匹配、效应量与置信区间齐备、多重比较校正、P 值不被当作效应大小。解读要区分「统计显著」与「实际重要」，并说明结论的适用边界。

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
