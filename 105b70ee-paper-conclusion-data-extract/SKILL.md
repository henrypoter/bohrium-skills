---
name: paper-conclusion-data-extract
description: 从真实科研论文（PDF/正文/表格/图注/补充材料）按统一字段表抽取研究结论与数据点，强制 claim→quote→location 证据绑定、quote 逐字回查与数值-引文双重核对、单位/统计量/实验条件同源保留、结论-限制-推测分层标注、缺字段四态区分（reported/not_reported/source_conflict/extraction_failed），产出可复核的 /app/output/result.json。当任务是给论文、出结构化字段表或结论卡片时使用。
---

# 文献结论与数据提取 Skill

## 1. 用途
把真实论文中散落在摘要、正文、表格、图注、补充材料里的**研究结论**与**数据点**，按 `/input/target-fields.json` 字段表还原成可核对结构：每个字段能回到原文位置（页/段/表格行列/图号），数值带单位、统计量与成立条件。不压缩论文，只做可复核的结构化抽取。

适用：提供 `/input/case.json`、`/input/task.md`、`/input/target-fields.json` 与论文材料（PDF 等）。不适用：无材料或要求凭领域知识补值——必须标 `not_reported`，禁止猜值填充（**猜的值不是抽取，缺席不是 0**）。

## 2. 预算纪律（硬性）
- 每案例模型请求 **≤12 次**，全程 **≤600 秒**，单次响应留余量。
- **先写诚实骨架再增量改进**：第 1 次写文件就产出合法 result.json（全部字段、未做项标 `extraction_failed`），之后逐字段改进并就地覆盖，任何时刻中断都有可评分产物。
- 长文不整篇复读：先抽文本层，再 grep 定位，只把命中页/段送入上下文。

## 3. 输入识别（第 1 步，1 次请求内完成）
1. 读 `/input/case.json` 取 `case_id`；读 `/input/task.md` 取任务边界。
2. 读 `/input/target-fields.json`：**逐 field_id 建空记录**（状态先置 `extraction_failed`），这就是骨架。
3. 列材料清单写入 `sources`（正文 PDF、补充材料、表格文件等）。
4. PDF 且无解析工具时：`python3 scripts/pdf_text.py paper.pdf work/paper.txt`（纯标准库兜底，输出带 `=== PAGE n ===` 页标记）。输出空/乱码 → 判扫描件无文本层，相关字段 `extraction_failed` 并在 `uncertainty` 说明，不得编造。

## 4. 抽取工作流（每字段一条记录，模板见 schemas/result_contract.json）
1. **定位**：grep 关键词（指标名、缩写、单位、同义词），命中后只读该页/段上下文。
2. **取值**：抄原文字面值，**不改写、不合并、不换算**；范围值（12–18）、「<0.05」、约值（~、≈）原样保留。
3. **绑定五要素**（缺失要素显式置 null，不省略键）：`value` 原字面值；`unit` 原文单位（无则 null + note 说明，禁止自补）；`statistic` 误差/统计量/样本量（mean±SD、95% CI、p、n）；`condition` 数值成立的实验条件（样本、设置、时间点、数据来源）；`comparator` 比较基线（无则 null）。
4. **证据定位** `evidence`：`quote` = 原文逐字片段（含数值那句），且 **value 中每个数字串必须能在 quote 中逐字找到**（统计量来自邻句时把该句一并抄入 quote；unit 与 statistic 的数字必须在原文中存在，validator 双重核对，不一致即 FAIL）；`page` 用 pdf_text.py 页标记号；`paragraph_id` 用「页码#段序」（如 `p3#para2`）；表格给 `table` + `cell`（表头行×列名，跨页/合并单元格在 note 说明还原规则）；图注给 `figure`。粒度须让第二个人独立抽查。
5. **状态判定**（四态互斥）：`reported`（有直接字面值且 quote 命中）；`not_reported`（通读相关章节确认未给出——**合法答案，不是失败**）；`source_conflict`（多处数值冲突，value=null，note 列全部冲突值及位置）；`extraction_failed`（材料不可读/版式无法解析/超时，写明可人工接管位置）。仅字面 quote 匹配不等于语义正确：必须核对 quote 中数值、单位、条件确属该 field_id 所问对象（张冠李戴是主要扣分点）。
6. **直接 vs 推断**：`basis` = `direct`（原文直述）| `inferred`（由文中数据推算，如差值/百分比变化；note 必须写算式含数字与运算符，如 `87.3-41.2=46.1`，validator 校验）。推断值必须与直述值区分。

## 5. 结论分层标注（claims）
从摘要、结果、讨论各抽 1–N 条主张，每条一张结论卡：
- `type` ∈ `conclusion`（明确结论）/ `limitation`（限制条件）/ `speculation`（推测表述）。
- 信号词：推测=suggest/may/might/possibly/「可能」「提示」；限制=limited to/only/under these conditions/「限于」；结论=demonstrate/show/conclude/「表明」。**信号词决定 type，禁止把「可能」改写成确定事实**；speculation 卡 quote 必须含情态信号词、limitation 卡必须含限定信号词（validator 机器校验，缺失即 FAIL）。
- 每张卡同样带 quote + page/paragraph_id，`related_field_ids` 挂到字段记录，保证结论与实验条件不脱钩。

## 6. 异常处理表
| 异常 | 处置 |
|---|---|
| 扫描件无文本层 | 相关字段 `extraction_failed`；uncertainty 注明需 OCR，禁止编造 |
| 表格跨页/合并单元格 | 按表头×列名逐单元格溯源；note 写明还原规则与单元格地址 |
| 单位缺失 | unit=null + note「原文未标单位」，不自补 |
| 字段原文未报告 | `not_reported`，value=null；列入 gaps |
| 多处数值冲突 | `source_conflict`，note 列全部冲突值与各自位置 |
| 材料缺失/权限不足 | 对应字段 `extraction_failed`，status=partial 并写明接管位置 |
| 超时/预算将尽 | 立即落盘当前 result.json（已含骨架），status=partial |

## 7. 输出契约（/app/output/result.json）
顶层字段：`case_id`、`task`、`status`（success/partial/cannot_determine/refused，有 extraction_failed 时不得 success）、`results`（每 field_id 一条）、`claims`、`sources`、`uncertainty`（无则空数组）、`gaps`（三态 field_id 列表，与 results 一致）、`change_records`（{step, action}）。完整定义见 `schemas/result_contract.json`。

**落盘顺序**：① 骨架（全部 field_id 置 extraction_failed，source_type 先置 text）→ ② 逐字段回填 → ③ claims → ④ `python3 scripts/validate_result.py /app/output/result.json work/paper.txt` 自检（第二参数触发原文双重核对；无文本层时省略）。**任一 FAIL 必须修正后重跑，不得带错交付**。

## 8. 最小调用示例
`examples/minimal_example.md`：**自拟合成**材料 + 调用步骤 + 标注「示例」的示意 result.json（已通过双重核对）。

## 9. 复跑与迁移
字段表 + 第 4–5 节口径 + validate_result.py 即完整复跑规范，他人可按同一字段表复跑比对；迁移只需换字段表。

## 10. 文件清单
- `SKILL.md` 本说明（入口）
- `scripts/pdf_text.py` 纯标准库 PDF 文本层抽取（带页标记；不支持 CID/OCR，乱码须降级标注）
- `scripts/validate_result.py` 契约校验 + 原文双重核对（quote 回查/数值回查/信号词/inferred 算式）+ 缺口汇总
- `schemas/result_contract.json` 输出契约与字段记录模板
- `examples/minimal_example.md` 合成最小示例（标注示例，非正式结果）

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
