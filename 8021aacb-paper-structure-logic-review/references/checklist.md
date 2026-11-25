# 六维结构诊断清单（判据+动作词表+修改权限）

每条诊断强制四元组：dimension/location(锚点)/criterion(判据)/evidence(≤40字)，外加 type/severity(high/mid/low)/action。只报能指认原文证据的问题；风格偏好不算错；拿不准进 uncertainty。
诊断无命中：diagnosis 可为空，但必须在 result.json 的 dimensions_checked 列出已逐维核查的维度并在 summary 写明「逐维核查无发现」；不得为凑覆盖虚报缺陷。
skeleton 信号：zone=AZ 区域须核实；论点—论据支持边由模型逐对判定引原文短语。redundancy 候选 channel=shingle/semantic_proxy/role；非 shingle 与 role 候选须 LLM 仲裁。

## 六维 source-grounded 修改方案（必须显式交付，见 result.json.dimension_plan）
- edit_plan.md 按六维分节（研究问题对齐/章节结构/论证链/段落关系/重复内容/结论边界），每节：有发现→列 diagnosis 条目（location+criterion+evidence）+ 对应 edit 动作（anchor→target）；无发现→写「逐维核查无发现」。
- result.json 的 dimension_plan 逐维给 status（diagnosed/no_finding）+ diagnosis_ids/edit_ids；与 diagnosis、edit_plan 交叉一致（result_check.py 校验）。
- 每条 edit 必须 source-grounded：ref_diagnosis 指回原诊断，anchor 指回原文位置；不得给出无出处的笼统建议。
- 可编辑 JSON/Markdown 即满足交付；revised_draft.md 仅在存在 L1/L2 句子级落笔时产出，整篇重写非必需。

## 1. 研究问题与贡献对齐 (research_question)
- 引言有无可指认研究问题句；是否在方法/结果/结论均有呼应。`logic_audit.py scan` 给 RQ 候选，`verify` 强制逐条 RQ 填齐锚点：closed 必须四环合法，open 必须有关联 diagnosis；不得只写“覆盖研究问题”而不给逐环证据。
- 贡献逐条核对：能否在结果节找到证据段；找不到→"贡献无证据"。
- 方法解决的子问题集与引言问题集不一致→"问题与方法各说各话"。

## 2. 章节结构与叙事顺序 (section_structure)
- 结论性内容是否先于证据；必要铺垫（定义/假设）是否后置。
- 篇幅失衡：用 zone_stats+各节占比；某节>50% 或方法/结果节<10% 标记。
- 同级标题粒度不一、该合并的相邻短节、该拆分的多主题长节。

## 3. 论证链与论据对应 (argument_chain)
- 闭环：问题→方法→结果→结论四段链各给锚点；断环处即诊断点。
- 逐条论断(claim/goal 段)找支撑论据(evidence 段/图表/引用)：无支撑→"论据缺失"；论据先于问题→"倒置"；结论当论据→"循环论证"；只覆盖部分→"强度不足，需收窄"。
- 判据须写"X 范围内检索到的 evidence 句=[锚点列表]"，不许只写"逻辑不严密"。

## 4. 段落关系 (paragraph_relation)
- 相邻段主题跳跃且无过渡句；一段多主题（拆分点给句子锚点）。

## 5. 重复内容 (redundancy)
- 三因素=相似度+论证角色+位置：两处同论证功能且非必要呼应（引言预告 vs 结论回顾=echo 不算）才判冗余。
- shingle→回原文确认近逐字重复；semantic_proxy→LLM 仲裁；role→LLM 判定是否换说法重复。
- 方法描述/术语密集句天然表层相似；相似度分数≠重复结论，防误报。

## 6. 结论边界与表述尺度 (conclusion_boundary)
- boundary_candidates+复核：结论/摘要逐句与结果节证据范围比对：超范围→"结论越界，需收窄"；相关+因果并存→"因果越界"；无限定词→"缺限制声明"。新增 CB 逐条比对 results 的人群/条件/样本/数值/设计：结论出现结果中未见数值时不得判 within/narrower；broader 必须有 diagnosis。禁止补写实验结论。

## 编辑动作词表（edit_plan.action 只能取这些）
move(锚点→目标) | merge(锚点列表→目标) | split(锚点→拆分点) | narrow(锚点,原句→收窄句) | add_transition(位置,过渡句) | delete(锚点,理由) | rewrite_sentence(锚点,原句→新句,理由)
结构性动作只给指令+对照锚点；句子级动作才给原句→新句→理由留痕。

## 修改权限分级（硬性）
- L1 语法/连接词/标点：可自动改，落 change_log(level=L1)。
- L2 句内重组/衔接：可自动改，改后作者确认；落 change_log(level=L2)。
- L3 数字/实体/否定/引用/结论方向：只给建议（edit_plan+human_confirmation），永不落笔、不得进 change_log。
- L1/L2 改写跑 result_check.py 事实保持校验（数值/引用/实体/否定词 diff）；漂移无解释→回退 L3 并补 fact_note。result_check 只记 ADVICE 不阻断（仅不可解析/交付缺失 FAIL）。
- 越权请求（补实验、改结论、增删文献主张）拒绝并标 human_confirmation。

## 异常处置
- 缺章节/无参考文献/图表缺失/格式混乱/截断：记 material_gaps 或 anomalies，status=partial，只诊断可读部分。截断须额外保留 scan 的 signals、last_anchor、last_text_sha256 与 read_scope；不能只写“可能截断”而继续 success。
- 逻辑问题无法自动修复（缺实验、数据不支持）：只诊断+human_confirmation，不硬改。
