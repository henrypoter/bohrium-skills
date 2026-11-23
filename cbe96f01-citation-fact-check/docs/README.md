# 引用与事实核验

## 用途
本题聚焦**引用支持与事实核验**。不查「有没有引用」，查「引的对不对」：被引文献是否支持该论断的方向、是否为二次转引、关键论断是否缺引用；同时核数值与单位在文内是否自洽。每条必须写出被引文献的实际结论与本文论断的差异。

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
