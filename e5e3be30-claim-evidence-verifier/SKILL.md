---
name: claim-evidence-verifier
description: 文献证据溯源与事实核验。对 /input/claims-to-verify.json 中的科研论断逐条做蕴含判定（supported/partially_supported/contradicted/insufficient_evidence），给出逐字引文与页/段定位、数值比对与冲突说明，产出 /app/output/result.json。适用：论断核查、引用核验、证据卡片。不适用：无源材料的自由问答、凭空要结论的请求（应拒答并说明）。
---

# claim-evidence-verifier：论断-引文对齐核验

## 何时触发 / 不触发
触发：「核验这些论断」「检查引用是否支持结论」「给这句话找原文依据」且存在源材料。
不触发：无材料或与文献核验无关——result.json 写 `status:"refused"` 并说明原因。

## 预算纪律（硬性，先保命再提质）
- 每案例 ≤12 次模型请求，全程 ≤600 秒；单次回复勿逼近 16384 tokens。
- **第 1 件事**：读 task.md、/input/case.json、claims 与材料清单后，立即用 `finalize` 写诚实占位 result.json（status=partial，已判多少写多少），再增量覆盖。
- 长论文：只对候选证据 ±1 段精读，不全文逐段喂模型。

## 四级判定定义
| verdict | 含义 | 判据 |
|-|-|-|
| supported | 文中直接支持 | 原文句子逐字蕴含论断，比较级/否定/显著性/条件全部保留 |
| partially_supported | 部分支持 | 复合论断只证成部分子判断；或数值一致但条件/范围被论断扩大 |
| contradicted | 不支持/矛盾 | 原文给出相反数值、相反方向或明确否定（≠ 未被实验推翻的外推） |
| insufficient_evidence | 材料未涉及 | 找不到蕴含所需证据；主题相关 ≠ 支持 |

规则：外推未被实验否证判 insufficient_evidence，不判 contradicted；来源冲突并列双方定位、取保守级。R1–R4 由 finalize 脚本记 advisory 提示（见下），终判以你读原文后的 verdict 为准，不强制改判。

## 标准流程（每案例）
1. **读输入**（1 次请求内完成）：`cat /input/claims-to-verify.json`；`ls /input`。PDF 无文本层时用环境工具抽为纯文本存 /app/work；抽不出 → 判 insufficient_evidence 并在 uncertainty 说明「PDF 无文本层」。
2. **prep 索引 + 三重对齐检查表**（0 模型请求）：
   `python3 /skills/weekly-skill/scripts/verify_claims.py prep --claims /input/claims-to-verify.json --source /app/work/paper.txt --out /app/work --topk 3`
   产出 verdicts.draft.json：复合论断拆成子论断（fact/comparison/causal/scope），每条子论断带候选句（file/page/para）与三重对齐检查表 alignment（entity_overlap、numbers_missing_in_quote、flags：entity_weak/scope_overreach?/hedged_evidence/says_unverified）及 machine_hint。machine_hint 只是初筛，终判由你读原文给出，但 flagged 项必须在 reasoning 里回应。
3. **逐论断判定**（每条 1 次请求，必要时 +1 次补查）：
   - 确认/修正 split_hint：复合论断必须拆开，不遗漏不重复；保留比较级、否定、显著性、适用条件。逐子项判定后合并：任一子判断被反驳→整体至多 partially_supported（关键断言被反驳则 contradicted）；只证成部分→partially_supported。
   - 选**最小充分证据**；候选不足取 ±1 段再读，仍无则 insufficient_evidence，绝不因主题相关判 supported（entity_weak 候选尤其警惕）。
   - **数值/单位逐字比对**写进 numeric_check（如 `claim 15% == quote 15%`、`claim 200 != quote 128`）。
   - 摘要与正文不一致、跨页证据、转引：以正文/原始数据处为准，两处定位都保留，limits 说明。
   - 填 verdict / evidence(quote 逐字复制+file+page+para+support) / reasoning / numeric_check / limits。
4. **finalize 校验落盘**（0 模型请求）：
   `python3 /skills/weekly-skill/scripts/verify_claims.py finalize --draft /app/work/verdicts.json --source /app/work/paper.txt --out /app/output --case-id <case_id>`
   脚本逐字核对 quote 是否真在原文（quote_verbatim，硬门槛），并对逐字命中引文生成 advisory 提示 R1–R4（记 rule_flags，不强制改判）：
   - R1 数值缺失/同单位不同值（抄错嫌疑）→ 提示复核；
   - R2 全称量化 vs 有限定语 → 提示复核范围夸大；
   - R3 引文仅称「尚未验证」而判 contradicted → 提示考虑 insufficient_evidence；
   - R4 证据同时带 supported+contradicted 标签 → 提示 limits 并列双方定位。
   支持度终判以你的 verdict 为准，advice 须在 reasoning 回应。硬门槛三条：quote 未逐字命中、verdict 非法/缺失、verdict≠insufficient 却无证据——命中记 ISSUE 并降 status=partial，修正后重跑或如实保留。
5. 剩余预算：复查 contradicted/partially_supported 的理由与冲突并列是否完整，重跑 finalize 覆盖 result.json。

## 异常处置
- 定位失败/无候选 → insufficient_evidence + uncertainty 说明检索范围；禁止编造引文（finalize 会抓出非逐字引文）。
- 引文与论断口径不一致（样本/单位/条件）→ partially_supported 或 contradicted，limits 写清口径差。
- 证据互相冲突 → 并列双方 quote+定位，verdict 取保守级；脚本以 R4 advice 提示（不强制改判）。
- 多子判断只有部分证据 → partially_supported，缺证子判断列入 uncertainty。
- 材料缺失/无法访问 → status=partial 或 failed，指出可人工接管位置。

## 输出契约（/app/output/result.json）
字段见 templates/result_template.json：case_id、status(success|partial|failed|refused)、claims[]（id/claim/sub_claims/verdict/evidence[quote,file,page,para,quote_verbatim,support]/reasoning/numeric_check/limits/rule_flags）、sources、uncertainty、summary、change_records。

## 自查（交付前必跑，0 模型请求）
`python3 /skills/weekly-skill/scripts/verify_claims.py selftest`：正向+变异双夹具（主题相关≠支持、数值抄错、外推≠否证、冲突并列记 advisory；编造引文硬拦截），10/10 PASS 再交付；FAIL 先修脚本。

## 文件
- scripts/verify_claims.py：prep/finalize/selftest 三阶段辅助，仅标准库，Python≥3.7。
- templates/result_template.json：输出骨架。examples/minimal_example.md：最小调用示例（合成材料，仅演示接口）。

判定分寸拿不准时回到上表：先问「原文是否逐字蕴含」，再问「条件是否被保留」。

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
