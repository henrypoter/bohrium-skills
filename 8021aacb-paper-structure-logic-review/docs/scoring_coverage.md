# 评分点逐项核对表（week3-road2-q5 论文结构与逻辑优化）

对照 PROBLEM.md 评分表逐得分点标注「已实现/部分/缺失 + 可复核证据」，未覆盖项如实声明。
可复跑证据：`python3 bench/fixture_test.py`（34 项，exit 0）、`python3 bench/path_compare.py`（exit 0）、`python3 scripts/result_check.py --selftest`（exit 0）。

## 一、实际效果（40）

| # | 评分点 | 状态 | 证据 |
|-|-|-|-|
| 1 | 任务完成度：对完整稿件完成结构诊断并交付作者可直接执行的修改方案 | **已实现** | SKILL.md 6 步工作流；edit_plan.md 为**六维 source-grounded 修改方案**（按六维分节：有发现→诊断(location+criterion+evidence)→动作(anchor→target)，无发现→「逐维核查无发现」）；result.json 的 dimension_plan 逐维给 status+diagnosis_ids/edit_ids；编辑动作限定词表（move/merge/split/narrow/add_transition/delete/rewrite_sentence）；revised_draft.md 仅为可选（L1/L2 落笔时产出，整篇重写非必需，对齐题目「full unsolicited rewrites are not required」） |
| 2 | 结果正确性：判断与稿件实际相符，不虚构缺陷、不漏真实断裂、不把风格偏好当结构错误 | **已实现（判据层）** | checklist 强制四元组+「风格偏好不算错」；fixture_test.py 夹具证明「正向零误杀（pos_zh/pos_en 十二项断言）、变异必命中（var_zh/var_en/var_nohead 九项断言）」；本轮先复现再修复 7 个真实 bug（见文末） |
| 3 | 结果完整性：覆盖研究问题/章节结构/论证链/段落关系/重复内容/结论边界六类，缺项不是主要问题 | **已实现** | checklist.md 六维判据；result_check.py 校验六维覆盖（diagnosis ∪ dimensions_checked）；诊断无命中须填 dimensions_checked 区分「无命中」与「未核查」（夹具：空诊断未声明必提示） |
| 4 | 结果可核验性：诊断与修改建议指回原文位置、判断过程可独立复核 | **已实现** | S1/S1.P2/S1.P2.s3 三级锚点；evidence≤40 字原文；每条 edit source-grounded（ref_diagnosis 指回诊断、anchor 指回原文）；锚点可用 skeleton 切分函数复算（path_compare.py resolve() 为参考实现）；result_check.py 对缺锚点/缺判据/缺证据逐条 ADVICE，并对 dimension_plan 与 diagnosis/edit_plan 的交叉一致性逐条校验（夹具 5/6 证明缺/错 dimension_plan 必提示） |

## 二、使用增益（25）

| # | 评分点 | 状态 | 证据 |
|-|-|-|-|
| 5 | 质量增益：同稿同任务下加载成果优于基础 Agent | **部分** | bench/path_compare.py 同稿双路径确定性对照：事实漂移(无解释) 2条4项→0、四元组诊断 0→2、L3 越权落笔→0。**未覆盖**：LLM 端到端质量对照需平台固定案例白板，本地不声称该分 |
| 6 | 效率增益：从诊断到定稿的时间、轮次与返工下降 | **部分** | 机制与口径已落地：每案例 ≤12 请求/≤600s、先写 partial 保底、脚本 0 请求（~4 万字符骨架实测秒级）、结构动作只给指令+锚点避免通篇重写返工、result.json budget 字段诚实填写。**未覆盖**：真实作者耗时/轮次的实测下降幅度，需平台对照 |
| 7 | 增益可验证性：同稿、同版本、同评分口径的对照 | **已实现** | path_compare.py：同一缺陷稿文件、同一脚本版本、同一组度量口径（事实漂移数/修改留痕数/锚点覆盖/诊断条目/产物数）；bench_report.md 显式声明这是流程级对照而非平台白板，并列不声称项 |

## 三、创新增益（15）

| # | 评分点 | 状态 | 证据 |
|-|-|-|-|
| 8 | 新增能力：论点—论据映射、跨章节冗余检测、结论与数据范围边界比对 | **已实现** | 论点图谱为工作流第 3 步（claim↔evidence 支持边引原文短语）；冗余=shingle+语义代理双通道+role 召回（无标题稿按段分组仍命中）；边界=强因果/相关当因果/缺限制声明三类候选（含无结论节标题时的结尾段回退通道） |
| 9 | 方法改进：章节功能拆解、论断抽取、重复识别、边界检查本身有实质改进 | **已实现** | AZ zone 功能分类+zone_stats 篇幅占比；断句英文缩写保护（Fig./et al. 锚点不偏移，夹具证明）；复述召回词汇倒排预筛使长稿 87.9s→2.3s（实测）；语义相似度改标准库 difflib C 加速近似 |
| 10 | 创新证据：证明相对已有方案（尤其语言润色类工具）的边界与增量 | **已实现** | docs/positioning.md：与 Grammarly 式润色/大纲式结构检查/基础 Agent 直接改写的 8 行能力矩阵，互补关系与 5 条「不做什么」边界声明；增量证据挂接 bench 两项可复跑脚本 |

## 四、可靠体验（10）

| # | 评分点 | 状态 | 证据 |
|-|-|-|-|
| 11 | 调用与易用性：Agent 正确触发，作者按说明完成一次完整诊断 | **已实现** | SKILL.md frontmatter name/description 含触发条件；6 步工作流+异常表+诚实规则；examples/minimal_example.md 最小示例（标注"示例"）；docs/data_formats.md §1 安装自检三命令 |
| 12 | 运行稳定性：不同学科、稿件类型、篇幅与重复运行下持续产出 | **部分** | 已夹具覆盖：中文/英文、有标题/无标题、空稿、~4 万字符超长稿（秒级）、非学术体裁、截断稿；脚本确定性输出（重复运行一致）。**未覆盖**：多学科真实长稿与双栏 PDF 实测（PDF 依赖外部转文本，已在限制声明） |
| 13 | 异常处理：缺章节/无参考文献/图表公式缺失/格式混乱/稿件被截断等的识别与处置 | **已实现** | SKILL.md 异常表 12 行（含空稿 empty_input、非学术体裁 no_academic_structure、超长稿 dup_scan_capped、诊断无命中）；截断检出、缺章节 missing_sections、体裁告警均有 fixture_test 实测断言 |

## 五、生态贡献（10）

| # | 评分点 | 状态 | 证据 |
|-|-|-|-|
| 14 | 文档完整性：使用说明、依赖、配置、示例、适用范围、限制和维护信息 | **已实现** | SKILL.md（用途/预算/工作流/异常/诚实规则/示例/资源）；docs/data_formats.md §1 安装与维护（零依赖、Python≥3.7、改词表后必跑回归的维护纪律）；docs/positioning.md §3 边界声明 |
| 15 | 资源可复用性：Skill 本体、脚本、题集、标注模板、论点—论据映射表等 | **已实现** | data_formats.md §2–§6 完整 schema（锚点/skeleton.json/result.json/交付物留痕约定/判据词表样例）；checklist.md=结构问题标注模板；bench/fixtures=题集；全部纯文本、标准库、无私有格式 |
| 16 | 分享推广价值：可分享的结构问题分类、典型案例、改稿前后对照与应用价值 | **已实现** | 六维问题分类+判据词表（checklist/data_formats §6）；典型案例=bench 正负夹具+minimal_example；改稿前后对照=change_log 格式+bench_report 双路径对照表；应用价值=positioning.md 能力矩阵 |

## 本轮修复的真实 bug（先复现后修，均有夹具防回归）

1. 无标题稿复述检测整体失效（所有句子同节被跳过）→ 按段分组（var_nohead 命中）。
2. 无标题稿结论边界检测失效（只认节标题）→ 结尾段启发式回退通道（var_nohead S1.P3 命中）。
3. 长稿复述召回 O(n²)：36k 字符 87.9s → 词汇倒排预筛+difflib 近似 → 2.3s。
4. 英文缩写断句（Fig./et al.）致句锚点偏移 → 缩写保护，变异稿种植句锚点由 s3 修正为 s2。
5. 空稿无任何告警 → empty_input 告警。
6. 非学术体裁无提示且可能被套学术判据 → no_academic_structure 告警+抑制结构误判。
7. result_check 对「诊断无命中」误报六维未覆盖 → dimensions_checked 字段区分无命中/未核查。

## 未覆盖项（如实声明）

1. **LLM 端到端诊断质量对照**（评分点 5）：平台固定案例白板由组织方生成，本地仅有流程级确定性对照，故标「部分」。
2. **真实作者耗时/轮次下降幅度**（评分点 6）：本地只能保证机制与度量口径，幅度需平台对照，故标「部分」。
3. **多学科真实长稿与双栏 PDF 实测**（评分点 12）：现有夹具为自拟样例（中/英、有/无标题、空/超长/截断/非学术），真实稿复杂度未覆盖，故标「部分」。
4. 语义代理通道为标准库近似（非神经嵌入），换说法重复最终判定依赖 LLM 仲裁——属设计边界而非缺陷，已在 positioning.md §3 声明。
