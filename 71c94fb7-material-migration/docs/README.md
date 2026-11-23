# 科研资料收集与迁移

## 用途
本题聚焦**采集与迁移的完整性**：跨来源采集记录来源与权限，字段映射显式（源字段→目标字段+转换规则），迁移前后做哈希/条数/关键字段校验，失败可续传且不重复上传。

## 调用
输入 `/input/case.json` 与 `/input/task.md`；输出 `/app/output/result.json` + 产物。

## 命令
```bash
python3 scripts/auto_tool.py  # 见下
```
`trace result.json`（依赖/环/状态/续跑点/幂等键/权限范围）/ `resume result.json`（算出可续跑步骤）/ `schema result.json`

## 模板
`templates/flow_spec.md`

## 自测
```bash
python3 bench/bench_run.py   # 10/10
```

## 适用边界
处理给定材料；不声称在线全覆盖；模型判定为待人工确认的建议。
