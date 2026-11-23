# 阅读批注与知识沉淀

## 用途
本题聚焦**批注到知识条目**：批注要带原文位置与引用片段，沉淀出的知识条目能回指到具体批注与文献，避免「摘要式复述」。重复/冲突的知识条目要合并或标注，而不是并列堆放。

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
