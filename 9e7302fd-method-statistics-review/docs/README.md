# 研究方法与统计审查

## 用途
本题聚焦**方法设计与统计报告**：对照是否排除对应混杂、样本量与效能是否支撑结论强度、检验方法是否匹配数据结构、是否报效应量与不确定性、多重比较是否校正。判据要写清「缺哪个对照会让哪个替代解释无法排除」。

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
