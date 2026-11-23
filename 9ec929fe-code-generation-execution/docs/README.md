# 科研代码生成与执行

## 用途
本题聚焦**分析代码的生成与真实执行**。代码必须真跑通并留下运行输出与依赖版本，失败要贴真实报错并按报错定位修复，不得只交一段看着对的代码。结果数值同样要能 `recheck` 复算。

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
