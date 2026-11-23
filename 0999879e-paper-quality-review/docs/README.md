# 论文质量审查

## 用途
本题聚焦**论文整体质量审查**。六类检查项逐类过一遍，重点在误报控制：每条问题的 quote 必须逐字存在于原文（跑 `verify --text` 核验），同一处不重复报，拿不准的进 `unchecked` 而不是凑数。产量不是目标，经核验的命中率才是。

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
