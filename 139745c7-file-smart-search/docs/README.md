# 科研文件智能检索

## 用途
本题聚焦**文件级检索**：按内容而不只按文件名检索，给出命中片段与文件位置，并说明检索范围（检索了哪些目录、哪些类型、哪些没进索引）。空结果要区分「确实没有」与「索引未覆盖」。

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
