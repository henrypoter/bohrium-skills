# 实验参数优化建议

## 用途
本题聚焦**参数可行域与多目标权衡**：从设备手册/材料规格/安全阈值抽出上下限与互斥关系，用 `params --spec` 逐项核验不越界；说明响应指标口径与不确定度、搜索策略（网格/序贯/贝叶斯）与停止条件，以及成本受限时牺牲多少响应可接受。

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
