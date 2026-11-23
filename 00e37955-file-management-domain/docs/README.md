# 科研资料管理领域总课题

## 用途
本题为**科研资料管理领域总课题**，覆盖落库、检索、分类、批注沉淀与知识库问答。要求交付可复跑的归档：目录规范先在、内容哈希去重、版本链清楚、每个文件都有 manifest 行与操作日志。

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
