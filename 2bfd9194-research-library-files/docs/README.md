# 科研资料库与文件管理

## 用途
本题聚焦**落库与版本管理**。去重按内容哈希而非文件名；同名不同内容进版本链并标 current/history；空文件与软链必须显式处置。`checkmap` 的路径违规与缺失元数据必须清零，不留没有 manifest 行的文件。

## 调用
输入 `/input/case.json` 与 `/input/task.md`；输出 `/app/output/result.json` + 产物。

## 命令
```bash
python3 scripts/file_tool.py  # 见下
```
`inventory batch/`（哈希/重复组/版本链/异常）/ `checkmap library/ --spec spec.json`（路径与必填元数据）/ `schema result.json`

## 模板
`templates/directory_spec.md`

## 自测
```bash
python3 bench/bench_run.py   # 10/10
```

## 适用边界
处理给定材料；不声称在线全覆盖；模型判定为待人工确认的建议。
