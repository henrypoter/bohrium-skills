# Bench 报告：判据夹具回归 + 同稿双路径对照（自拟样例，非平台白板）

复跑：`python3 bench/fixture_test.py`（exit 0/1）；`python3 bench/logic_bench.py`（exit 0/1，写 logic_bench_results.json）；`python3 bench/path_compare.py`（exit 0，写 bench_results.json）。
全部夹具为自拟短材料，仅验证流程与判据口径，不代表平台正式案例难度。

## 1. 判据夹具：正向零误杀、变异必命中（34 项全过，exit 0）

| 组 | 夹具 | 断言 | 结果 |
|-|-|-|-|
| 断句单元 | 内联构造 | `Fig. 1`/`et al. (2023).` 不碎句、句锚点不偏移 | PASS ×2 |
| 正向零误杀 | pos_zh / pos_en（结构完整、结论有限定词） | 近逐字跨节复述候选(shingle·cross)=0；边界候选=0；截断/体裁/空稿误报=0 | PASS ×12 |
| 变异必命中 | var_zh / var_en | 种植跨节复述对 (S2.P1.s1,S3.P1.s2) 命中；强因果越界结论 S5.P1 命中 | PASS ×6 |
| 变异必命中 | var_nohead_zh（无标题） | 段间复述对 (S1.P1.s1,S1.P2.s2) 命中；结尾段强因果 S1.P3 经回退通道命中 | PASS ×3 |
| 异常场景 | empty / non_academic / 截断稿 / 超长稿(~40k 字符) | 空稿 exit0+empty_input 告警；非学术体裁 exit0+no_academic_structure 告警且不产生结构误判；截断检出 truncation_suspect；超长稿 <20s 完成且结构完整 | PASS ×6 |
| 契约回归 | result_check | 诊断无命中+dimensions_checked → 0 告警；空诊断未声明 → 提示；缺判据 → ADVICE 不阻断；不可解析 → FAIL exit 1；--selftest 双夹具 exit 0 | PASS ×5 |

「零误杀」口径：仅把 channel=shingle 且 position=cross 的近逐字候选与边界候选视为可能直接成判的信号；semantic_proxy/role 候选按设计必须 LLM 仲裁（checklist §5），属提示而非判定。

## 2. 新增 RQ / 边界 / 截断审计（20/20，exit 0）

`logic_bench.py` 以同一自拟完整短稿构造 3 个正向断言（候选定位、完整稿零截断/零数值越界、verify 通过）和 17 个单点变异：
- scan 4 项：缺结果环、结论新增结果外数值、无限定普遍化、末句截断全部命中；
- verify 13 项：输入哈希、漏审 RQ/CB、closed 缺方法、open 无诊断、错结论/结果锚点、broader 无诊断、错版本、结果外数值仍 within、截断哈希/状态被改、截断未 partial 或缺处置全部命中。

本 bench 验证的是“候选—人工裁决—机检留痕”的闭环，不把关键词/数值差集当成自动科学判决。RQ 隐含表达可能漏召回，scan 无候选时仍需人工补录；具体边界见 `docs/scoring_coverage.md`。

## 3. 同稿双路径对照（path_compare.py，实测输出）

同一缺陷稿（var_zh / var_en）：
- 路径 A（无诊断直接重写的确定性模拟）：通篇逐句改写、去引用标记、数值模糊化、无锚点无留痕；
- 路径 B（本 Skill 流程）：skeleton 信号 → 四元组诊断 → L1 删除留痕、L3 收窄只建议不落笔、事实保持 diff。

| 口径 | A 无诊断直接重写 | B 诊断-改稿流程 |
|-|-|-|
| 事实漂移（无解释，条/项） | 2/4（两稿一致） | 0/0（删除留痕经 fact_note 解释） |
| 修改留痕数 | 0 | 1（原句→新句→理由→锚点） |
| 锚点可复核修改 | 0 | 1（100%） |
| 四元组诊断条目 | 0 | 2 |
| L3 越权落笔 | 结论句被直接改写（无权限概念） | 0（1 条收窄仅作建议） |
| 产物数 | 1（整篇改写稿） | 4（diagnosis/edit_plan/revised_draft/skeleton） |

## 4. 诚实边界（不声称项）

1. 本报告是**流程级确定性对照**：路径 A 是对「无诊断直接重写」类别典型失败的确定性模拟，不是对平台基础 Agent 的实测；LLM 端到端质量对照以平台固定案例白板为准，本地不声称该维度分数。
2. 夹具为自拟短材料，用于判据回归（防误杀/防漏报/防回归），不代表真实论文复杂度。
3. 语义代理通道为标准库词汇 Dice + difflib 近似（非神经网络句嵌入），换说法重复的最终判定依赖 LLM 仲裁。
4. 效率口径（请求数/秒数）在 result.json `budget` 字段诚实填写；本 bench 脚本 0 模型请求。
