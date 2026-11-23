# 笔记结构 schema（note_schema.md）

每条笔记一个条目，字段：

| 字段 | 取值 | 说明 |
|-|-|-|
| id | N1... | 唯一 |
| kind | question/method/conclusion/reusable/doubt | 笔记类型（问题/方法/结论/可复用要点/待验证疑点） |
| claim | 文本 | 本条论断（一句话） |
| support | 数组 | 支撑，每条 {annotation_id 或 quote, location} |
| source_file | 文件 | 来源文献（逻辑文档） |
| tags | 数组 | 主题/标签/实体 |

硬规则：
- 每条 claim 至少 1 条 support，support 必须有 location（页/段）。
- 摘抄不等于笔记：只有 quote 没有 claim/support 结构的不算。
- doubt 类必须写清"待验证什么、缺什么证据"。

批注 → 笔记：一条批注可支撑多条笔记；一条笔记可聚合多条批注。映射关系保留（annotation_id）。
