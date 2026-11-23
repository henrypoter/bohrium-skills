# 论文逻辑与论证审查

## 用途
本题聚焦**论证链**：结论是否超出证据（相关说成因果、体外推体内）、是否存在未排除的替代解释、讨论是否回应反例、章节间是否自相矛盾。每条要同时引「结论句」与「证据句」两处原文，做对照，而不是只给一句评语。

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
