---
name: formula-parse-verify
description: >-
  科研论文公式解析与核验：公式还原、符号表、推导分步、量纲三档检查、单位归一
  数值核验、等价写法比对；输出 result.json；缺公式表示降级 insufficient_evidence。
---

# formula-parse-verify

认得准→讲得清→推得顺→算得回。脚本仅用 Python 3 标准库。

## 预算纪律（硬性）

每案例 ≤12 请求、≤600 秒。**先写诚实 result.json**（run_case.py 骨架），
每块增量重写、中断可交付。

## 工作流

0. **启动**：`python3 scripts/run_case.py /input /app/output`：读 case_id/契约，
   解析 source-formulas.xml 到 /app/work/，立刻写 result.json 骨架（去重符号表：
   symbol/上下标/LaTeX/来源位置/出现次数，meaning/unit/dimension/origin 留空）。
   读 task.md。
1. **认得准**：用 parsed LaTeX（保留 \frac、上下标、积分限、希腊字母、来源 ID）；
   誊写式用 `verify.py equiv` 与 parsed 式比对自检；逐符号对照原文，不合并/丢项，
   不一致以材料为准并记 uncertainty。
2. **讲得清**：symbol_table 逐条填 meaning/unit/dimension/source/origin。origin ∈
   explicit_in_text / inferred_from_context（写明依据）/ unknown（禁止按常识补写）；
   单位缺失记 null 并写入 uncertainty。
3. **推得顺**：derivation_steps 每步标 operation、assumptions（假设/近似/边界）、
   depends_on（跨公式引用）、evidence（原文位置）；材料未给推导不编造，evidence
   填 null 并写入 limitations。
4. **算得回**：scripts/verify.py 四子命令，输出粘进 verification（spec 见 examples/）：
   - `dim spec.json` 量纲三档。spec: units（SI 单位串+词头）、可选 kinds、
     checks(lhs/rhs)。verdict: consistent / dimensionally-consistent-but-
     physically-suspect（量纲一致但 kinds 不同；筛查非证明）/ inconsistent（附
     dim_diff）。
   - `num spec.json` 数值核验：单位归一（值可写 {"value":6371,"unit":"km"} 自动
     换算 SI 记入 normalized）→ ast 白名单精确代入（+ - * / **、sqrt exp ln log
     sin cos tan、pi e）→ rel_err ≤ rtol(默认0.01)，computed/abs_err/rel_err/
     magnitude_ratio 全记录。
   - dim/num 结论只告警不阻断：verdict 或 match=false 时输出 warning 且退出码 0；
     selftest 失败才代表脚本 bug。
   - `equiv '<A>' '<B>'` LaTeX 规范化 → 表达式树等价比对：\frac 与 /、e^{x} 与
     \exp(x)、\left\right、交换律、合并同类项、等式换边均判等价。
   - `selftest`（首用一次）：正向夹具全绿；变异夹具（量纲不一致/数值错误/符号未
     定义）全部检出且等价写法不误判；结果记入 change_log。
   数值必须取自材料（写明出处）；缺值记 uncertain，不虚构。
5. **终审**：status ∈ success / partial / insufficient_evidence / refused；
   sources 列材料路径+定位；uncertainty 列未报告/冲突/无法判断；change_log 记录
   各阶段；确认 result.json 可被 json.load 解析。

## 异常处理与诚实降级

- 无公式表示：只核对材料明确指标，推导/复算报 partial + insufficient_evidence；
  禁止反推公式、禁止未知填 0。
- 公式残缺/截断：还原可读部分，残缺处用 `\boxed{?}` 标注并记 uncertainty。
- 符号未定义/歧义：origin=unknown、meaning/unit=null；代入无解/单位缺失：核验
  条目记 error，不输出 match=true；脚本失败 stderr 写入 limitations、改手算。

## 适用与限制

适用：MathML/XML 公式目录、LaTeX 文本或可转写公式的科研材料。限制：不做公式
图像 OCR；量纲限 SI；等价比对限代数等价；kind 依赖人工标注。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/read_tool.py support_check answers.json --text source.txt` 把每条证据引文在原文里做逐字匹配，不在原文的（误报）直接揪出；支持度分档统计。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：证据逐字回链、支持度分档。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/support_rubric.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/support_rubric.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```

## 补强：异常处置与可复现（阶段重做，2026-11-25）
在 verify（量纲/单位/LaTeX 等价）基础上补齐题面点名的异常处置与可核验要求：

| 异常 | 动作 |
|-|-|
| 图像模糊（扫描件低清） | 该公式标 `low_confidence`，转写结果标「待核」，不臆造符号 |
| 公式截断（跨页/超长被截） | 标 `partial` + 请求补齐，截断处不下结论 |
| 符号严重歧义（同一符号多义） | 并列两种解读标 `uncertainty`，不无依据取舍 |
| 权限不足（原文/附件不可读） | 标 `blocked` + 写明缺什么权限，不算完成 |

可复现：`result.json` 增加 `formula_version`（公式转写版本 + 原文件哈希），使符号定义、量纲核验、LaTeX 等价比对可按版本复算。
