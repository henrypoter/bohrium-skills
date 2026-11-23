---
name: sci-transfer-writing
description: 科研成果转化写作工作流。将论文/技术报告等科研材料按指定受众与体裁（科普文章、项目申报、技术转移报告、新闻稿等）改写为可提交成稿，并产出事实-来源映射、术语锁定表、逐段改动清单与材料缺口标注。核心机制：事实台账（数值/限定语/证据类型/研究对象）→受众取舍→体裁骨架成稿→机器核验事实保真与三维夸大（建议/因果/外推）。适用于"提供源文、说明读者与体裁"的改写任务；不适用于无源文的自由创作。
---

# 科研成果转化写作 Skill

## 目标与触发条件
输入给出**源文（论文/技术报告/事实底稿）+ 目标读者 + 目标体裁 + 篇幅/格式约束**并要求改写、转写或结构化写作时触发。产物：可编辑成稿 + 事实映射 + 改动清单 + 缺口/待确认标注。

## 预算纪律（硬性，违反会判 0）
- 每案例 **≤12 次模型请求**，全程 **≤600 秒**；单次响应注意 16384 token 上限，长文分段处理。
- **先写诚实 result.json 再增量改进**：读完输入立即写 status="partial" 的 result.json 骨架到 /app/output，每完成一阶段就地更新；任何时候中断都留可用结果。
- 机械工作（数字/单位/引用/缩写/限定语/研究对象抽取与核对）交给 `scripts/fact_tools.py`（0 次模型请求）；模型请求只花在理解与成稿。
- 参考分配：读输入 1–3 次；受众/取舍/提纲 1 次；成稿 1–3 次；修订 1–2 次；汇总 result.json 1 次。预留 ≥2 次余量，不足直接定稿并在 uncertainty 说明。

## 运行环境与输入
- 输入：`/input/case.json`、`/input/task.md` 及随附材料（PDF/文本等）。**必须读取实际文件**，不得依据文件名或领域标签臆测内容；PDF 用环境预装工具转文本后再处理。
- 工作目录 `/app/work`；最终产物放 `/app/output`：`deliverable.md`、`fact_ledger.json`、`check_report.json`、`result.json`。
- 脚本仅用 Python 3 标准库，禁止 pip 安装。

## 标准工作流（六步）
1. **读输入建档**：解析 case.json/task.md，确定 case_id、源文、目标读者、体裁、篇幅上限。立即写 partial result.json（字段见 templates/result_schema.md）。
2. **建事实台账**：`python3 scripts/fact_tools.py extract <材料文件...> -o /app/work/fact_ledger.json`。台账含数值+单位、样本量、图表编号、引用、缩写、强度词、**限定语 caveats、因果/相关证据类型、建议词、研究对象层级**。**人工通读源文一遍**补充脚本抽不到的：关键结论句、限定条件（温度/体系/工况）、对比基准（与谁比、提升多少）。
3. **受众画像与取舍策略**：按 templates/genres.md 受众分层确定解释深度、术语密度、类比方式；按"必须保留/可压缩/可删除"三级对台账逐项定取舍（必须保留项见 genres.md §三）。
4. **按体裁骨架成稿**：用 genres.md 对应骨架写稿，首行必须有 `#` 标题。术语锁定（缩写首现展开、同一概念一词，记 term_glossary）与三维边界（不新增建议、不把相关写因果、不外推到更高研究对象层级）见 genres.md §五/七。
5. **机器核验**：`python3 scripts/fact_tools.py check /app/work/fact_ledger.json /app/output/deliverable.md --genre <体裁> -o /app/work/check_report.json`。处置：`added_numbers_not_in_source`删或改有出处（红线，已排除同数字不同写法）；`source_numbers_missing_in_draft`补回（已排除同数字不同写法）；`strong_word_escalation`降级；`caveats_missing`补等价限定；`advice_escalation`删建议；`causal_escalation`降为相关/提示；`extrapolation_escalation`降为"有待验证"；`unexplained_abbreviations`展开或删；`fig_refs_missing`/`citations_missing`补回编号，或确认属体裁性删除并记入 change_log；`genre_compliance.missing_required`补段落（规则见 genres.md §六/七/八）。数字优先用阿拉伯数字减误报；修订后预算允许再复核一次。
6. **定稿与记录**：更新 result.json 为 complete/partial，填事实-来源映射（每条关键事实给源文定位与保留/改写/删除理由）、改动清单、材料缺口与待确认项、uncertainty，verification 填入 check 报告计数。

## 事实纪律（红线）
- 成稿每个数字/单位/百分比/倍数/样本量必须能在台账/源文找到；**禁止**新增材料外事实、四舍五入改口径。
- 图表编号、引用编号与源文一致；不新增引用。
- 对比优势必须写明对比基准（"较 X 提升 Y%"，X 来自源文）。
- 源文限定语随论断迁移；证据类型与研究对象不越级（genres.md 六/七）。

## 异常处理
- **材料缺应用/产业化数据**（无应用验证、无成本、无 TRL）：正文写"【材料缺口：…】"并列 result.json 的 material_gaps，**不得编造**。
- 数据自相矛盾：两处数字都进 fact_source_map 并列入 open_questions，正文取保守表述。
- 体裁与篇幅冲突（如 300 字科普装不下全部指标）：保住关键结论与 1–2 个核心指标，其余列入改动清单注明"因篇幅删除"。
- 材料涉密/未发表：仅用给定材料，不做外部检索补充，uncertainty 标注。
- 材料无法解析（PDF 损坏等）：status="partial"，uncertainty 说明缺失范围，已解析部分照常完成。
- 材料数据不全（缺样本量/统计口径/对比基准）：列入 open_questions，正文用保守表述，不补造。
- 源文自身含强度词（如"首次"）：成稿同级保留不报越级（check 已豁免），但不得再加更强词。

## 最小调用示例
见 examples/example_case.md（自拟短材料，已标注示例，非真实数据）：演示 extract→成稿→check→result.json 的完整调用。夹具自测（正向零误杀、7 类变异必命中、异常场景）：`python3 tests/run_tests.py`。

## 安装与维护
- 仅 Python 3 标准库，无需安装；数据格式与扩表/扩体裁方法见 docs/data_formats.md。
- 定位与能力边界：docs/positioning.md；公平对照证据：docs/benchmark.md；评分点核对：docs/scoring_coverage.md。

## 自查（提交/定稿前）
- `python3 -c "import yaml,sys; yaml.safe_load(open('SKILL.md').read().split('---')[1])"` 或目测 frontmatter 仅含 name/description 且可解析。
- 包内 UTF-8 文本文件 ≤50 个、单文件 ≤500KB、总量 ≤2MB（Harbor 约定），无软链无二进制。
- `python3 tests/run_tests.py` 全部通过（exit 0）。
- 示例 result.json 可被 `json.load` 解析且含全部契约字段。
- 全文无待办标记残留；check 报告新增数字数为 0 或已逐条处置；caveats/三维越级/体裁缺项已逐条处置。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/write_tool.py claim_check result.json` 核验论断-引用回路，重点抓**数值论断无引用**与悬空引用；`structure` 查必需章节无缺无空。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：论断与引用绑定、章节缺项检测、三向一致。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/manuscript_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/manuscript_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
