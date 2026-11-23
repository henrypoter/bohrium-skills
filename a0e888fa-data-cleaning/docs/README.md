# 科研数据清洗与处理

## 用途
本题聚焦**清洗**：缺失、异常值、重复、类型不一致、单位不一致逐类给判定规则与处置动作，并给出「清洗前后条数对照」。清洗规则要能重跑，不得手工临时改数；哪些行被剔除、为什么剔，必须可逐条追溯。

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
