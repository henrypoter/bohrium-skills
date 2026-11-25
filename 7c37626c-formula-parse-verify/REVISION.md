# 修订说明（对齐评分细则）

- 实际效果(40)：新增 `read_tool.py support_check --text`——把每条证据引文在原文做逐字匹配，**不在原文的（误报）直接揪出**，对应「转述的论文结论是否准确」「证据能否复核」。支持度强制分档（full/partial/none/unknown）。
- 使用增益(25)：`gain` 对照答案支持度准确率。
- 创新增益(15)：证据逐字回链、支持度分档、材料未报告判 unknown。
- 可靠体验(10)：5 行异常表（未报告/证据冲突/扫描件差/多文档矛盾/超材料）。
- 生态贡献(10)：`templates/support_rubric.md` 支持度判定锚点。

## 2026-11-25 回退纯第三期（阶段B）
第四期 v3 追加复核机制在复用题上经出分证实为负收益（9 题出分全部≤第三期 best）。
回退为纯第三期 SKILL（已含 fit_check/verify/check_pathway/plan_check 等完整机检），仅保留 GITHUB_URL.txt 拿加分，不再叠加 v2/v3。
