# 文献综述生成 v2.0.0

完整输入、工作流程、异常表和 result.json 契约见 `../SKILL.md`。判对核心是：筛选决定引用已声明判据；论断有纳入文献的具体位置与原文摘录；主题有归纳依据且覆盖纳入集；冲突、空白均保留证据锚点；版本和来源哈希可独立复算。

## 快速验证

```bash
python3 scripts/syn_tool.py schema bench/fixtures/good_result.json
python3 scripts/syn_tool.py screen_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py evidence_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py grounding_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py provenance_check bench/fixtures/good_result.json \
  --input bench/fixtures/case.json --source-root bench/fixtures/sources
python3 bench/bench_run.py
```

fixture 为纯合成接口示例，不是正式案例输出。正式结果还必须运行 `cite_check`、`theme_check`，并使用 `/input` 实际材料重新生成。
