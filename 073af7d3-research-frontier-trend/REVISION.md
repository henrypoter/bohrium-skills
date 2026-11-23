# 修订说明（重做）

本题 v1 因 harness evaluation_error 无分。本轮**重做**（非修改），换专用趋势分析方案：

- 专用工具 `trend_tool.py trend_check`：每条趋势论断必须带 `year_range` + 引用 + 定位；主题演化必须有 stage+period；研究空白必须有排除证据。这直接对「趋势判断是否由文献支撑、空白是否有据」。
- 口径先锁：`analysis_version` + 时间窗/指标/年度分布口径，防口径漂移。
- 拐点归因：每条趋势说清「何时因何变化」，代表作覆盖各阶段。
- 异常处置 5 行：无年份/低样本/口径难对齐/空白无证据/趋势与分布矛盾。
- 模板 `templates/trend_spec.md` 可复用。
