# 科研数据库查询与分析

## 用途
本题聚焦**跨表查询与分析**。两个高频错误必须防：漏写连接条件导致行数膨胀（聚合前先验 `count(*)` 基数）、编码型字段当连续变量算均值。查询逻辑、连接键、聚合粒度都要写明，结论数值必须能 `recheck` 复算。

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
