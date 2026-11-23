# 最小调用示例（示例，自拟短材料，非正式案例结果）

> 以下输入与输出均为本 Skill 自拟的演示材料，仅说明接口与流程，不代表任何正式案例。

## 示例输入

`baseline.md`（稿件基线摘要）：
```markdown
# 一种快速排序变体在小样本上的性能
## 摘要
我们提出 QS-Lite 算法。实验表明其性能良好。
## 方法
QS-Lite 在基准排序上加入采样枢轴策略。
## 结果
在 1000 条随机数据上，QS-Lite 平均耗时 12 ms。
```

`comments.md`（意见摘要）：
```markdown
Reviewer 1
Comment 1: 样本量太小，作者应补充 10 万条规模数据的实验，并报告方差。
Comment 2: 摘要中"性能良好"表述模糊，请改为量化结论并引用"平均耗时 12 ms"的出处。
Reviewer 2
Comment 1: 方法节未说明枢轴采样比例，请澄清。
```

## 调用方式

```bash
SKILL=/skills/weekly-skill
python3 $SKILL/scripts/revision_kit.py inventory baseline.md comments.md /app/work
# -> items=3 subs=3 mismatch_quotes=0（>0 表示意见引用原文在稿件中找不到，标注疑似误解）
# comments_parsed.json 含 类型/严重度/处置级别(L1-L4) 建议值
python3 $SKILL/scripts/revision_kit.py matrix /app/work/comments_parsed.json /app/work/matrix.md
# 先写 result.json(partial 骨架) → 建台账 → 真实改稿 → 写回复信
python3 $SKILL/scripts/revision_kit.py verify /app/output/revised_manuscript.md \
    /app/output/response_letter.md /app/work/comments_parsed.json /app/work/verify_report.json
# -> 覆盖/锚点可检索(回填行号)/决策词/反驳合规/语气风险 五查
python3 $SKILL/scripts/revision_kit.py trace baseline.md /app/output/revised_manuscript.md /app/output/changes.diff
```

## 示意输出（示例片段，非正式结果）

回复信 R1.1 块（无法补做场景）：
> **立场**：无法执行 **动作**：未补做实验，结果节补充"仅基于 1000 条数据、未报告方差"的局限说明 **证据/理由**：材料不含 10 万条数据与实验条件 **替代方案**：引用基线已有结果（平均耗时 12 ms）**缓冲语**：感谢审稿人指出样本规模问题 **修改位置**：结果节，锚点：「仅基于 1000 条数据、未报告方差」

result.json 示意（字段名以实际 case.json 的 output_contract 为准）：
```json
{
  "case_id": "example-demo", "status": "partial",
  "deliverables": {"revised_manuscript": "/app/output/revised_manuscript.md",
    "response_letter": "/app/output/response_letter.md",
    "mapping_table": "/app/output/mapping_table.md",
    "changes_diff": "/app/output/changes.diff"},
  "sources": [{"item": "R1.1", "decision": "无法执行",
    "evidence": "baseline.md 结果节：平均耗时 12 ms"}],
  "uncertainty": ["R1.1 要求的大样本实验超出材料范围，无法补做"],
  "change_log": ["结果节新增局限说明（锚点：仅基于 1000 条数据）", "摘要量化改写"]
}
```
说明：status=partial 因一条意见无法执行已如实标注；其余闭环。若全部闭环则 complete。
