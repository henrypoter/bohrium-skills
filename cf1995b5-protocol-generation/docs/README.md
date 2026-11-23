# 实验方案生成与优化

## 用途
本题聚焦**从目标到可排期方案**：假设可被推翻、变量有操作定义与单位、对照说明排除哪类混杂、参数逐项核对设备量程（`params --spec`）、风险三件套齐全。不要复述目标或套通用流程。

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
