# 最小调用示例（自拟材料，仅演示接口，非正式案例结果）

`src.txt`（英→中，空行分块）：

```
Perovskite solar cells have reached a certified power conversion efficiency of 26.1% in 2023 [12].

The stability remains limited to about 1.5万 hours under 85 °C (Smith et al., 2022).

Figure 1. Device architecture.
```

`glossary.tsv`（源术语、锁定译法、禁用译法）：

```
perovskite solar cell	钙钛矿太阳能电池	钙钛矿太阳电池
power conversion efficiency	光电转换效率
stability	稳定性
```

```bash
cd /app/work
SK=$SKILL_DIR/scripts
python3 $SK/chunker.py src.txt -o blocks.jsonl --plan plan.json
python3 $SK/check_terms.py parse glossary.tsv -o glossary.json
# 模型按 plan.json 翻译 → tgt_blocks.jsonl
python3 $SK/align.py blocks.jsonl tgt_blocks.jsonl -o /app/output/bilingual.md \
  --report /app/output/align_report.json --emit-translation /app/output/translation.md --direction en2zh
python3 $SK/check_terms.py check --src src.txt --tgt /app/output/translation.md --glossary glossary.json -o /app/output/terms_report.json
python3 $SK/check_integrity.py src.txt /app/output/translation.md -o /app/output/integrity_report.json
python3 $SK/selftest.py $SK
```

示意输出（示例）：terms_report.json `pass=true, severity.critical=0`；integrity_report.json `pass=true, normalization_notes 含 1.5万=15000, semantic.flags=[]`；align_report.json `pass=true`；三脚本 exit 0（advisory，读 flags）。result.json 参照 templates/result.template.json。

> 注：均为自拟示例，非正式案例或预期答案。
