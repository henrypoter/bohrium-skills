# 实验结果解释与异常分析

## 用途
本题聚焦**趋势、异常点、原因与复核**：趋势给区间与拟合方式，异常点给判定阈值与与对照的偏离，原因按证据强度排序并写排除证据（防把相关当因果），复核步骤要写成第二个人能照着做，后续实验建议对应具体证据缺口。

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
