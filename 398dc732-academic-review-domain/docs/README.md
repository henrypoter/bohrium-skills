# 学术审查领域总课题

## 用途
本题为**学术审查领域总课题**，覆盖事实核验、引用支持、方法设计、统计报告、论证链、学术规范六类，不要求每类都查到底。要求给出可交办的问题清单：每条有原文定位与原句引用、经逐字核验、标严重度，并显式写出已查与未查范围。

## 调用
输入 `/input/case.json` 与 `/input/task.md`；输出 `/app/output/result.json` + 产物。

## 命令
```bash
python3 scripts/review_tool.py  # 见下
```
`verify issues.json --text manuscript.txt`（引文逐字核验，揪出误报）/ `summary issues.json`（六类覆盖矩阵）/ `schema result.json`

## 模板
`templates/checklist.md`

## 自测
```bash
python3 bench/bench_run.py   # 10/10
```

## 适用边界
处理给定材料；不声称在线全覆盖；模型判定为待人工确认的建议。
