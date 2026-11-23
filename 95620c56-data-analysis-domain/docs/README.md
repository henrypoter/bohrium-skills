# 科研数据分析领域总课题

## 用途
本题为**科研数据分析领域总课题**，覆盖查询、清洗、可视化、代码执行与统计解读。要求先画像、再计算、必复算：每个上报数值都在 `aggregates` 里声明并用 `recheck` 从原始数据重算通过，血缘（快照版本/表/筛选/连接键）完整。

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
