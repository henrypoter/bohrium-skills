# 最小调用示例（示例，非正式案例结果）

> 本目录均为参赛者**自拟演示材料与示意输出**，非平台正式案例结果。

输入（自拟）：`materials/ch1_intro.md`。指令（自拟）：①"88.1%"改为"88.1%（数据来源：示例参考文献 [1]）"；②"目前还没有数据"润色为"相关数据尚待补充"。

```bash
export AWC_ROOT=/app/work/awc AWC_OUT=/app/output AWC_INPUT=/input
S=../scripts/awc.py
python3 $S init --case-id demo-example --title "示例稿件"
python3 $S add-chapter ch1 --title "引言" --file materials/ch1_intro.md
python3 $S revise ch1 --anchor "准确率为 88.1% [1]" \
  --new "准确率为 88.1%（数据来源：示例参考文献 [1]）" \
  --reason "指令①：补充来源定位" --source "materials/ch1_intro.md 第3行"
python3 $S revise ch1 --anchor "目前还没有数据" --new "相关数据尚待补充" \
  --type polish --reason "指令②：润色" --source "指令文本"
python3 $S accept 1 ; python3 $S reject 2   # 1 采纳、2 拒绝并回退
python3 $S claim --text "准确率 88.1%" --evidence "88.1%" \
  --source "materials/ch1_intro.md" --locator "ch1 引言"
python3 $S claim --text "对照实验结果"    # 无证据 → needs-human
python3 $S verify
python3 $S status
python3 $S export    # md/.tex/.docx + PDF + readback
python3 $S result --case-id demo-example
```

示意输出：`sample_result.json`（节选）。要点：revise 锚点找不到时退出码 3 且不改稿；reject 自动回退；无证据/查不到证据的 claim 进入 `confirmations_needed`；正文 `[1]` 未建文献表时 `readback.refs` 标 `unresolved` 并写入 limits——两者共同使 `status=partial`；`export_report.readback` 记录全部回读核对结果。
