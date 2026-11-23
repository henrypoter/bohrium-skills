# 实验方案可行性评估

## 用途
本题聚焦**可行性与资源核验**：设备型号/精度/附件与现有条件比对（已具备/可外协/需采购/不具备四态）、耗材货期、样本量与来源、伦理审批级别与时长。审查意见要落到方案的具体章节与清单行，「有条件可行」必须写清是哪些条件。

## 调用
输入 `/input/case.json` 与 `/input/task.md`；输出 `/app/output/result.json` + 产物。

## 命令
```bash
python3 scripts/exp_tool.py  # 见下
```
`check result.json`（六要素与参数自洽）/ `params result.json --spec limits.json`（越界/单位/未声明限值）/ `schema result.json`

## 模板
`templates/plan_spec.md`

## 自测
```bash
python3 bench/bench_run.py   # 10/10
```

## 适用边界
处理给定材料；不声称在线全覆盖；模型判定为待人工确认的建议。
