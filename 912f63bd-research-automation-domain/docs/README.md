# 科研软件插件与自动化领域总课题

## 用途
本题为**科研软件插件与自动化领域总课题**，覆盖跨站任务、资料迁移、浏览器插件与网页阅读翻译。要求步骤依赖成 DAG、状态随手记录、失败可断点续跑、跨站数据有权限范围。

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
