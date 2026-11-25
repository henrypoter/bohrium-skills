# 研究方法与统计审查（v3.0.0）

审查研究设计、变量定义、统计方法、样本量/效能、结果报告五面，并交叉记录事实、引用、设计、统计、论证、规范六类。每条问题绑定原句、细粒度定位、quote/来源内容哈希、缺陷类型、严重度、依据与修改建议。

## 运行

无需安装第三方依赖，Python 3 标准库即可。输入 `/input/case.json`、`/input/task.md` 和实际材料；工作文件在 `/app/work`，结果在 `/app/output/result.json`，原始 output_contract 字段必须保留。

```bash
python3 scripts/review_tool.py preflight --text manuscript.txt --manifest manifest.json
python3 scripts/review_tool.py verify issues.json --text manuscript.txt
python3 scripts/review_tool.py statcheck stats.json
python3 scripts/review_tool.py coverage result.json        # partial 加 --allow-partial
python3 scripts/review_tool.py schema result.json          # 基础兼容检查
python3 scripts/review_tool.py gate result.json            # 严格交付总闸
python3 scripts/review_tool.py summary issues.json         # 仅问题计数，不代表覆盖
```

命令格式、manifest/stats 输入示例、异常恢复表与 result 字段算法见 `SKILL.md`；审查锚点见 `templates/checklist.md`。

## 最小合成示例与自测

`bench/fixtures/sample_paper.txt` 和 `good_result.json` 是合成接口示例，不是组织方正式案例或预测答案。执行：

```bash
python3 bench/bench_run.py
```

测试每个新命令的正向零误杀及破坏性变异必命中；日志末尾的当前通过数才是有效结果，不在文档预写固定成绩。

## 边界

工具不自行解析 PDF/OCR、不访问网络、不自动理解全部统计模型。p-CI 仅用于常见双侧区间；特殊方法转 pending。版本哈希和结构校验不证明语义判断正确，正式增益必须来自同输入真实对照。缺页、扫描失败、图表不可读、统计输出缺失、材料不足必须诚实 partial/failed，语言混杂不是缺陷。
