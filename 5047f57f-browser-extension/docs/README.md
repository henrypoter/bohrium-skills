# 学术浏览器插件

## 用途
本题聚焦**浏览器内科研操作**：在真实页面跑通并交出可用产物，抓取的字段与位置能与原文逐项对上（不得错位），权限范围与数据外传边界写明，失败时能解释失败原因并给出可复跑的记录。

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
