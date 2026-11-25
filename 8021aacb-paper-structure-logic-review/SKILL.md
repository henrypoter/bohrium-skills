---
name: paper-structure-logic-review
description: 论文结构与逻辑优化 Skill。对稿件/提纲做六维结构诊断（研究问题对齐/章节结构/论证链/段落关系/重复内容/结论边界），产出可复核诊断报告、可执行修改方案与逐条留痕。输入论文初稿/投稿稿/提纲且要求结构诊断或修改建议时触发。
---

## 1. 用途与适用条件
- 输入：稿件（markdown/txt；PDF 用 pdf-text-tool 转文本）或提纲；全稿诊断+修改，提纲只诊断不硬改。
- 输出（/app/output）：diagnosis.md、edit_plan.md（六维 source-grounded 修改方案，必需可编辑）、skeleton.json、logic_audit.json、result.json；revised_draft.md 可选（仅当有 L1/L2 句子级落笔，整篇重写非必需）。
- 判据见 references/checklist.md；字段模板见 references/result_schema.json（含 dimension_plan、artifact_version、input_manifest、logic_audit）。

## 2. 预算纪律
- 每案例 ≤12 次模型请求、≤600 秒；单次回复 ≤16384 tokens；长稿分块。
- 先写 status=partial 的 result.json 保底，后续就地更新。
- 脚本仅标准库；失败不阻塞，异常记 result.json。

## 3. 工作流（6 步，锚点先行）
1. **读输入**（0 次）：读 /input/task.md、case.json，按 case.json 找实际稿件读真实内容（不凭标签猜）；提取 case_id、受众/文体/格式约束。
2. **跑骨架与新增候选审计**（0 次）：`python3 /skills/weekly-skill/scripts/skeleton.py <稿件> -o /app/work/skeleton.json`，再跑 `python3 /skills/weekly-skill/scripts/logic_audit.py scan <稿件> -o /app/work/logic_audit.json`。前者得 AZ zone/复述；后者给 RQ 问题句、CB 结论句、结果外数值/普遍化候选、截断末锚点/末文哈希与真实输入 SHA-256。立即写 status=partial 的 result.json 保底。候选不是诊断，须逐步裁决。
3. **论点图谱与研究问题闭环**（1-2 次）：逐条 RQ 填 method/result/conclusion 锚点；只有四环真实对应才标 closed，断环标 open 并关联 research_question diagnosis_ids，不适用写 not_applicable+理由。找不到不得标“未找到”后跳过；verify 的 Q1-Q4 会抓漏审、错锚与无诊断 open。另逐条 claim↔evidence 支持边并引原文短语。
4. **六维诊断与结论—数据边界比对**（2-3 次）：按 checklist 逐维查。每条强制四元组（dimension/location/criterion/evidence）+ type/severity/action；脚本信号回原文核实；channel≠shingle/role 候选须 LLM 仲裁；无问题不报。每条 CB 把结论与 **results 节**人群/条件/样本/数值/因果限定逐项比对，填 within/narrower/broader/uncertain+理由+结果锚点；结果外数值不能写 within/narrower，broader 必须关联 conclusion_boundary diagnosis。核查后无命中的维度仍填 dimensions_checked 并在 summary 说明。
5. **修改方案与修改稿**（2-3 次）：edit_plan.md 按六维分节（研究问题对齐/章节结构/论证链/段落关系/重复内容/结论边界），每节列 source-grounded 条目（诊断 location+criterion+evidence → 动作 anchor→target），无发现写「逐维核查无发现」；result.json 的 dimension_plan 逐维填 status+diagnosis_ids/edit_ids（与 diagnosis、edit_plan 交叉一致）。edit 只用词表动作并标 L1/L2/L3；结构性动作只给指令+锚点；仅当有 L1/L2 句子级动作才落 revised_draft.md 并写 change_log；L3（数字/实体/否定/引用/结论方向）只建议不落笔。无法自动修复只诊断+human_confirmation。
6. **落盘与双闸自查**（0 次）：复制 skeleton/logic_audit 到 /app/output，更新 result.json；跑 `python3 /skills/weekly-skill/scripts/result_check.py /app/output/result.json`，再跑 `python3 /skills/weekly-skill/scripts/logic_audit.py verify /app/output/result.json /app/output/logic_audit.json`。前者仅不可解析/交付缺失 FAIL，其余 ADVICE 仍须处理；后者 P/Q/B/T 错误均为硬 FAIL（exit 1），必须修正，不得把截断或未审 RQ/CB 静默写成 success。

## 4. 异常处理（不中断）
| 情况 | 处置 |
|-|-|
| 缺章节/无参考文献/图表公式缺失/格式混乱 | material_gaps；只诊断可读部分，status=partial |
| 疑似截断 | logic_audit.truncation 保留 signals/末锚点/末文SHA-256；material_gaps 写“只读到何锚点、缺哪些后文”，anomalies 写末句未终止/代码围栏/悬空标题信号；status=partial、read_scope=partial，只诊断已读部分，T1/T2 防静默 |
| 输入是提纲 | 只出 diagnosis+edit_plan，revised_draft 标"提纲阶段不代写" |
| 逻辑问题无法自动修复 | 诊断+human_confirmation，不代改 |
| 稿件与任务/标签冲突 | 以实际文件为准，记 uncertainty |
| 空稿/无文本内容 | skeleton 告警 empty_input；status=partial，material_gaps 记"空稿"，不编造诊断 |
| 非学术体裁（新闻/公告等） | skeleton 告警 no_academic_structure；只给体裁提示与可读性建议，不套学术六维硬判 |
| 无标题结构稿 | 段即分组单元照常复述检测；结尾段启发式承担结论边界检查（候选需核实） |
| 超长稿 | 分块读入；skeleton 词汇倒排预筛（~4万字符实测秒级），dup_scan_capped=true 时记 anomalies |
| 诊断无命中 | dimensions_checked 填六维+summary 说明；不得为凑数虚报缺陷 |
| 脚本失败 | 手工分节继续，anomalies 记录 |

## 5. 诚实性规则
- 诊断、留痕、数字、引用须回溯到实际输入与锚点；不新增材料外事实。
- sources 列实际读取的输入路径；input_manifest 必须原样采用 logic_audit.scan 的真实 SHA-256/bytes，artifact_version 与 rule_version 不得省略；budget 填真实请求数与秒数。
- material_gaps/uncertainty/anomalies 不混用。

## 6. 最小调用示例
见 examples/minimal_example.md（自拟短材料，输出标注"示例"）。正式案例由平台提供，不含预制答案。

## 7. 资源清单
- scripts/skeleton.py：骨架提取器（标准库，Python≥3.7）：锚点+AZ zone+复述候选+边界候选；复述命中记 warning；英文缩写保护断句；空稿/非学术体裁告警。
- scripts/logic_audit.py：`scan` 研究问题闭环候选、结论—results 数值/普遍化边界、截断证据和输入哈希；`verify` 硬检 P1/P2/Q1-Q4/B1-B6/T1/T2，结果可独立重跑。
- scripts/result_check.py：result.json 自查器；仅不可解析/交付缺失为 FAIL，其余记 ADVICE；`--selftest` 含正向+变异+无命中夹具。
- references/checklist.md：六维判据+动作词表+L1/L2/L3+异常处置。
- references/result_schema.json：result.json 字段模板（含 dimensions_checked）。
- examples/：最小调用示例。
- docs/：positioning.md（能力矩阵与边界）、data_formats.md（数据格式+安装维护+判据词表样例）、scoring_coverage.md（评分点逐项核对）。
- bench/：fixture_test.py（34 项判据+异常回归，exit 0/1）、path_compare.py（同稿双路径对照）、logic_bench.py（3 正向+17 变异，20 项）、fixtures/（自拟正负夹具）、logic_bench_results.json、bench_report.md。
- 安装维护见 docs/data_formats.md §1。限制：信号为启发式候选需模型核实；语义代理为标准库词汇/LCSS 近似，换说法重复靠 role 召回+LLM 仲裁。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/write_tool.py claim_check result.json` 核验论断-引用回路，重点抓**数值论断无引用**与悬空引用；`structure` 查必需章节无缺无空。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：论点与引用绑定之外，新增 RQ 四环逐条闭环、结论与 results 数值/条件边界比对、输入/末文双哈希及截断降级硬闸。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/manuscript_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/manuscript_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py       # 既有正向零误杀 + 变异必命中
python3 bench/logic_bench.py     # 新增 RQ/边界/截断：3 正向 + 17 变异
```
