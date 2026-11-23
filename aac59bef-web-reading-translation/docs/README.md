# 网页文献阅读与翻译

## 用途
本题聚焦**网页论文抓取与分语对照**：抓下来的必须是论文正文而非导航广告，正文/摘要/图表分离；译文逐段对得上原文并保留原文，术语全文一致并留术语表；读者能凭交付物回到原始页面核对每条内容。

## 调用
输入 `/input/case.json` 与 `/input/task.md`；输出 `/app/output/result.json` + 产物。

## 命令
```bash
python3 scripts/auto_tool.py  # 见下
```
`trace result.json`（依赖/环/状态/续跑点/幂等键/权限范围）/ `resume result.json`（算出可续跑步骤）/ `schema result.json`

## 模板
`templates/flow_spec.md`

## 自测
```bash
python3 bench/bench_run.py   # 10/10
```

## 适用边界
处理给定材料；不声称在线全覆盖；模型判定为待人工确认的建议。
