# 科研选题与创新性评估 v2.0.0

完整输入、四项交付、异常表和 result.json 契约见 `../SKILL.md`。核心判对闸：问题可证伪；检索日志可复跑；创新与最近邻逐维比较并回链原文；可行性前提有来源或显式假设；冲突与综合结论一致；输入/来源版本哈希可复算。

## 快速验证

```bash
python3 scripts/syn_tool.py schema bench/fixtures/good_result.json
python3 scripts/syn_tool.py question_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py search_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py novelty_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py feasibility_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py decision_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py provenance_check bench/fixtures/good_result.json \
  --input bench/fixtures/case.json --source-root bench/fixtures/sources
python3 bench/bench_run.py
```

fixture 为纯合成接口示例，不是正式案例输出。正式结果还需运行 `cite_check`，并用 `/input` 实际材料重新生成所有字段。
