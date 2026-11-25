# 证据库（evidence_library.json）字段模板

`{"evidence": [ ... ]}`，每条文献一个对象：

| 字段 | 含义 | 纪律 |
|-|-|-|
| id | E1, E2, ... | 全库唯一 |
| authors / year / title / venue / doi | 著录信息 | **只能抄自材料本身**；缺失填 null 并在 result.json 的 uncertainty 标注，禁止编造 |
| type | 原始研究 / 综述 / 指南 / 预印本 | 影响证据等级上限 |
| availability | full_text / abstract_only | 按实际可读范围填写；S1 必填，仅摘要触发封顶与定位核查 |
| locator | quote 的章节/页/段 | 仅摘要可得时填「摘要」，等级封顶 C |
| quote | 逐字原文摘录（可核验锚点） | 必须逐字；evidence_lib.py 会回原文做子串核验 |
| supports | 该文献真正支持的表述 | 写明支持到哪一步（不得比原文更强） |
| data | 关键数字（样本量、效应量、区间等） | 与 quote 同源 |
| conditions | 适用条件/人群/体系/方法前提 | 正文限定语的依据 |
| limitations | 作者自述或显然的局限 | 不确定性表达的依据 |
| evidence_level | A/B/C/D | 见 SKILL.md 第 4 节分级口径 |
| evidence_level_reason | 等级判定理由 | 必须写设计/样本/重复/共识如何决定等级，S4 拦截空理由 |
| strength_basis | {design,sample_size,replication,consensus,basis_unknown} | 四项均须显式；确实未知填 null 并把字段名列入 basis_unknown，禁止编造（S5） |
| caveat | 撤稿/版本差异/仅摘要等警示 | 无则 null；仅摘要必须在此再次标摘要（S3） |
