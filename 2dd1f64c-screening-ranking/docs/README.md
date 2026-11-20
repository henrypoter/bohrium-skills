# 文献筛选与智能排序

## 用途
加载后用协议化流程完成可复核的文献检索与筛选；输出 `result.json` + 标注/仲裁/审计工作表。

## 调用
1. 读 `/input/case.json` 与 `/input/task.md`，按 `templates/protocol.md` 写协议（含检索日期与标准版本）。
2. 检索 → `dedup` 去重 → 双人独立标注 → `agreement` 算 κ → 仲裁 → `audit` 校验闭合 → 写 `result.json` → `schema` 自检。
3. 输出到 `/app/output/`。

## 命令
```bash
python3 scripts/search_tool.py dedup     records.json     # 精确重复组 + 近似候选（预印本/正式版）
python3 scripts/search_tool.py agreement pairs.json       # 决策一致率 / Cohen's κ / 分歧清单
python3 scripts/search_tool.py audit     result.json      # 计数闭合 + 理由码族别一致性
python3 scripts/search_tool.py schema    result.json      # 交付契约校验
```

## 最小调用示例（示意，非正式案例结果）
`bench/fixtures/records.json` → `dedup`：5 条记录，检出 1 组 DOI 精确重复（R1/R2），并把 R1/R3 标为「标题一致 + 同年」的近似候选待裁决。
`bench/fixtures/pairs.json` → `agreement`：6 条双人标注，一致率 0.6667、κ 0.3333、3 处分歧（1 处理由码、2 处决策）。
`bench/fixtures/good_result.json` → `audit`：闭合通过（4→4→4）。

## 自测
```bash
python3 bench/bench_run.py     # 10 项：四命令正向零误杀 + 六处变异必命中
```

## 适用边界
- 只处理给定题录的**有限快照**；不声称在线全覆盖或全局召回率。
- 不替代同行评审与研究者最终判断；模型判定默认是「待复核建议」。
