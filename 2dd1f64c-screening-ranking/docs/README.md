# 文献筛选与智能排序

## 用途
加载后用协议化流程完成可复核的文献检索与筛选；输出 `result.json` + 标注/仲裁/审计工作表。

## 调用
1. 读 `/input/case.json` 与 `/input/task.md`，按 `templates/protocol.md` 写协议（含检索日期与标准版本）。
2. 冻结维度/权重/阈值/k → `dedup` 去重 → 全候选逐维评分（有真实双标注才用 `agreement`）→ 稳定排序与冲突隔离 → `schema` → `audit` → `rankcheck` 复算与异常硬闸。
3. 输出到 `/app/output/`。

## 命令
```bash
python3 scripts/search_tool.py dedup     records.json     # 精确重复组 + 近似候选（预印本/正式版）
python3 scripts/search_tool.py agreement pairs.json       # 决策一致率 / Cohen's κ / 分歧清单
python3 scripts/search_tool.py audit     result.json      # 计数闭合 + 理由码族别一致性
python3 scripts/search_tool.py schema    result.json      # 基础交付契约校验
python3 scripts/search_tool.py rankcheck result.json      # 加权复算 + 全候选/证据/Top-k/平局/异常硬闸
```

## 最小调用示例（示意，非正式案例结果）
`bench/fixtures/records.json` → `dedup`：5 条记录，检出 1 组 DOI 精确重复（R1/R2），并把 R1/R3 标为「标题一致 + 同年」的近似候选待裁决。
`bench/fixtures/pairs.json` → `agreement`：6 条双人标注，一致率 0.6667、κ 0.3333、3 处分歧（1 处理由码、2 处决策）。
`bench/fixtures/good_result.json` → `audit`：闭合通过（4→4→4）；→ `rankcheck`：总分复算通过，顺序 R1/R2/R3/R4，Top-4 一致，R3/R4 同分按 ID 稳定展示。

## 自测
```bash
python3 bench/bench_run.py     # 27 项：五命令正向零误杀 + 异常/排序变异必命中
```

## 适用边界
- 只处理给定题录的**有限快照**；不声称在线全覆盖或全局召回率。
- 不替代同行评审与研究者最终判断；模型判定默认是「待复核建议」。
