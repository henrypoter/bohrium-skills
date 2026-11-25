# 段落级改写记录模板

> 多文体正文骨架见 `genre_skeletons.md`；本模板只约束可复核性，不限定为 Results & Discussion。

```markdown
## task指定的小节
<面向目标读者的完整段落；保留关键样本、数字、单位、比较基准、条件与图表。>[S1]
```

对应 project.changes：

```json
{"segment_id":"section1-p1","action":"revise",
 "before_quote":"<原文中本段的逐字片段>",
 "draft_segment":"<上述完整段落，含[S1]且逐字一致>",
 "reason":"<task指令编号>；保留<证据>；压缩<冗余>；解释<术语>；边界<初步/相关/不确定>",
 "evidence_ids":["S1"]}
```

- 一段可引多条证据 `[S1,S2]`；每个数字与单位必须能在本句所引证据的 quote/surfaces 中逐字找到。
- `delete` 不写 draft_segment；required 证据不能因删除而从全文消失。
- `add` 只用于无外部事实的衔接；有事实就必须挂证据。
