# 检索协议模板（protocol.md）

> 填完后随 result.json 一并交付。协议版本号必须写死；后续任何标准改动都要升版本并在 `change_log` 记录「哪条标准、何时、为何、影响了哪些已判记录」。

## 1. 问题与范围
- 研究问题（一句话，可检验）：
- 拆解：对象 / 机制或方法 / 人群或样本 / 时间范围 / 比较关系 / 证据要求
- 边界：数据库范围、语种、文献类型、是否含预印本与灰色文献、时间窗起止

## 2. 检索式（每个库一行，逐条可复跑）
| 编号 | 数据库 | 检索式 | 字段 | 时间窗 | 语种 | 检索日期 | 命中数 |
|-|-|-|-|-|-|-|-|
| Q1 |  |  | title/abstract |  |  |  |  |

> 记录**检索日期**是复跑的前提。检索式与纳入标准的对应关系写在下一节每条标准后面。

## 3. 纳入/排除标准（逐条落到可判定判据，含版本）
| 标准编号 | 类型(纳入I/排除E) | 判据（可判定，不含"相关/合理"等模糊词） | 需要什么证据 | 对应检索式 | 版本 |
|-|-|-|-|-|-|
| I1 | 纳入 | 研究对象为 X 且 报告 Y 结局 | 标题或摘要出现 X 与 Y | Q1,Q2 | v1.0 |

## 4. 双人独立标注
- 标注者 A / B（可为人或模型，须写明是哪一个）；**独立标注，互不可见对方结果**。
- 一致率门槛：决策一致率 ≥ 0.80 且 Cohen's κ ≥ 0.60 视为可接受；未达标须重训标准或重标。
- 计算命令：`python3 scripts/search_tool.py agreement pairs.json`

## 5. 冲突仲裁
- 分歧类型：`decision`（纳/排相反）、`reason_code`（都纳但理由不同）、`evidence`（依据片段指向不同位置）。
- 仲裁人：______；仲裁必须写结论 + 依据，**不得用多数票或平均掩盖实质分歧**。
- 记录表：见 `worksheets.md` 仲裁表。

## 6. 计数闭合与审计
- 必须闭合：`原始 N → 去重后 M → 已判定 K（纳入+排除+待定）`，且 `M ≤ N`、`K = M`。
- 校验命令：`python3 scripts/search_tool.py audit result.json`（不闭合返回非零）。
- 审计日志逐行记录：步骤、输入数、输出数、操作人、时间、标准版本。

## 7. 参考集、覆盖与补检协议（先于结果冻结）
- 独立参考集：`version/frozen_at/source/denominator_rule/records[]`；禁止从候选反推分母。
- 逐条异常：撤稿证据与分母规则、identifier_conflicts、fulltext_status；无全文不移分母。
- 命中：`identifier/title_author_year/manual` 之一，留 evidence + matched_record_id；baseline/final 全矩阵。
- 漏检：M1–M5，按类型写具体 query_id/field/source 与证据。
- 补检：每轮 query/fields/source/run_date/status/target_miss_codes/new_hit_ids；新增只计 baseline miss→final hit，写 stop_rule。
- 硬闸：`python3 scripts/search_tool.py covercheck result.json`。

## 8. 增益对照（只有实际对照才能填）
- 使用同一冻结参考集、同一查询预算的基础 Agent / Skill Agent 原生结果，逐条比较 hit status、真实新增和残漏。
- 没有平台或实际运行对照就填 null + uncertainty；不编造准确率、κ、耗时、人工核对或榜单成绩。

## 9. 适用边界与不适用
- 本 Skill 处理的是**有限快照**（给定题录集合），不声称在线数据库全覆盖、不声称全局召回率。
- 不替代同行评审、不替代研究者的最终科学判断；模型判定默认是「待复核建议」。
