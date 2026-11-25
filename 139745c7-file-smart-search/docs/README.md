# 文献与资料自动分类

## 用途
本题聚焦**自动分类**：分类体系（目录/标签）先定义并可解释，每份文件的归类给依据（标题、关键词、内容片段），低置信度的标为待人工确认而不是硬塞一个类。要报告分类覆盖率与人工复核比例。

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
