# 学术规范与合规检查

## 用途
本题聚焦**学术规范与合规**：伦理审批与知情同意、数据可得性声明、利益冲突与基金标注、图像重复使用、作者贡献。缺项要指到具体章节位置，并注明依据哪份规范条目（期刊要求/机构规定），不凭印象说「不合规」。

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
