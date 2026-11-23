# 实验方案比较与选择

## 用途
本题聚焦**多方案横向比较**：先固定可比字段（目标/硬约束/成本口径/风险/证据强度）再逐方案填表，避免各写一套；成本区分一次性投入与按次消耗；给可辩护的选择与具体舍弃理由，并说明敏感性（哪个假设变了结论会翻转）。

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
