# 实验方案设计领域总课题

## 用途
本题为**实验方案设计领域总课题**，覆盖生成、比较、可行性、参数优化与结果解释。要求六类要素齐备、参数经设备量程核验、风险带触发与止损，并明确哪些内容需专家确认。

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
