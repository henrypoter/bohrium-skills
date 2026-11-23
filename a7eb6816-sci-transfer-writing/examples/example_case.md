# 最小调用示例（示例！材料为自拟虚构内容，非真实科研数据，非正式案例结果）

## 1. 示例输入（自拟短材料）
保存为 `/app/work/demo_source.txt`：

> 本研究制备了一种铋基光催化剂 BiOBr-X。在可见光照射 60 min 内，该催化剂对罗丹明 B（10 mg/L，100 mL）的降解率达到 92.4%，而未改性的 BiOBr 仅为 61.7%（图 2）。五次循环后降解率仍保持在 88% 以上。结果表明，氧空位的引入提升了载流子分离效率。该体系仅在实验室模拟废水中验证，实际工业废水中的效果尚待考察 [3]。

任务：改写为 300 字以内、面向公众的科普短文。

## 2. 调用步骤
```bash
mkdir -p /app/work /app/output
# 步骤A：建事实台账（0 次模型请求）
python3 scripts/fact_tools.py extract /app/work/demo_source.txt -o /app/work/fact_ledger.json
# 步骤B：模型按 templates/genres.md 的科普骨架成稿 → /app/output/deliverable.md
# 步骤C：机器核验（0 次模型请求；--genre 触发体裁结构检查）
python3 scripts/fact_tools.py check /app/work/fact_ledger.json /app/output/deliverable.md --genre 科普文章 -o /app/work/check_report.json
# 步骤D：按报告修订后写 /app/output/result.json（字段见 templates/result_schema.md）
```

## 3. 示意输出（示例，非正式结果）
成稿（节选，示例）：
> 科学家给一种叫 BiOBr 的材料做了改造，造出能借助阳光分解染料的新材料。实验中，它用 60 分钟就把 92.4% 的染料分子分解掉，而没改造的版本只能完成 61.7%；连续用 5 次后，净化能力仍保持在 88% 以上。研究小组认为，材料内部引入的"氧空位"帮助电荷更快分离。不过要提醒的是，这一结果目前只在实验室模拟废水中得到，真正工厂废水里的表现还需要进一步验证。

事实映射（节选，示例）：
- `92.4%` / `61.7%` / `60 min` / `88%`：kept，来自源文第 1–2 句；
- "氧空位提升载流子分离效率"：rephrased 为"帮助电荷更快分离"，论断强度保持"表明/认为"级；
- "仅在实验室模拟废水中验证"：kept 为局限句，未升级为"可治理工业废水"；
- 图 2、引用 [3]：deleted，理由"科普体裁不出现图表编号与文献编号"，已记入 change_log。

## 4. 该示例演示的异常处理
材料缺"实际工业废水效果"数据 → 正文保留限定句 + material_gaps 记"无实际废水体系数据"，不补造。check：added_numbers=0、caveats_missing=0、causal_escalation=0、extrapolation_escalation=0。

## 5. 更多自测与文档
夹具自测 `python3 tests/run_tests.py`（正向零误杀、7 类变异必命中、异常与稳定性 22 项）；评分点核对 docs/scoring_coverage.md；数据格式 docs/data_formats.md。
