# 数据格式 schema（data_formats）

本文件定义本 Skill 全部机器可读产物的格式，供他人直接复用（意见拆解结果、回复信块、闭环矩阵、核查报告、diff）。全部为 UTF-8 纯文本/JSON，无私有二进制格式；生成与解析代码仅标准库（`scripts/revision_kit.py`）。示例值均来自自拟夹具（bench），非正式案例。

## 1. comments_parsed.json（inventory 产物：意见拆解）

```json
{
  "comment_count": 3,
  "sub_requirement_count": 3,
  "items": [
    {
      "id": "R1.1",
      "reviewer": "1",
      "raw": "意见原文（合并行，去头）",
      "subs": [
        {"text": "子要求原文", "type": "数据",
         "severity_suggestion": "重大", "disposition": "L4"}
      ],
      "type": "数据",
      "severity_suggestion": "重大",
      "disposition": "L4",
      "quoted_missing": ["意见中引用但稿件里找不到的原文片段"]
    }
  ]
}
```

| 字段 | 含义 | 取值 |
|---|---|---|
| id | 意见编号 | `R<审稿人>.<序号>`；无审稿人前缀时为裸编号如 `1.1` |
| reviewer | 审稿人标识 | 原文中的编号/中文数字 |
| subs[].type | 类型建议 | 方法/数据/写作/格式/伦理 |
| subs[].severity_suggestion | 严重度建议 | 重大/次要/澄清/误解 |
| subs[].disposition | 处置级别建议 | L1 采纳/L2 部分采纳/L3 礼貌反驳/L4 拒绝执行 |
| quoted_missing | 疑似误解信号 | 意见引文在稿件全文中检索不到的片段列表 |

注意：type/severity/disposition 均为关键词词表**建议值**，最终判断由 Agent 复核。

## 2. anchors.json（inventory 产物：稿件锚点表）

```json
[{"kind": "heading", "line": 2, "text": "摘要"},
 {"kind": "para", "line": 3, "para": 1, "text": "段落前 40 字"}]
```
`kind`=heading/para；`line` 为 1-based 行号；用于起草阶段的稳定结构锚点（章节/段落）。

## 3. matrix.md（matrix 产物：三列闭环矩阵骨架）

机器生成的 Markdown 表，一行一个子要求：

```
| 原子意见（编号[类别/严重度/处置级别]） | 回复条目（决策+摘要） | 修改位置锚点（修订稿原文） |
| R1.1[数据/重大/L4] 子要求摘要(前48字) | [待填] | [待填] |
```
回复/锚点两列由 Agent 从真实改稿与 diff 回填；锚点须为修订稿原文片段（≥6 字）并能被 verify 检索。

## 4. verify_report.json（verify 产物：五查核查报告）

```json
{
  "comments_total": 3,
  "location_claims": 3,
  "anchor_locations": [{"anchor": "锚点片段", "line": 3, "heading": "摘要"}],
  "rebuttal_compliance": [{"item": "R1.1", "missing": "缓冲语"}],
  "tone_hits": ["理解有误"],
  "fail": [{"check": "coverage|location|rebuttal_compliance", "item|anchor": "...", "msg": "..."}],
  "warn": [{"check": "decision|tone", "msg": "...", "hits": []}],
  "status": "pass|warn|fail"
}
```

| 检查 | 级别 | 含义 |
|---|---|---|
| coverage | fail | 意见编号在回复信中找不到（边界匹配，R1.1 不被 R1.10 吞掉） |
| location | fail | 锚点引文在修订稿全文中检索不到（去空白、支持跨行） |
| rebuttal_compliance | fail | 反驳/无法执行条目缺证据/替代方案/缓冲语 |
| decision | warn | 决策词数少于意见数 |
| tone | warn | 命中对抗性措辞词表 |

`anchor_locations` 供定稿阶段把行号+标题回填回复信与映射表（锚点两阶段第二阶段）。verify 有 fail 时进程退出码为 1，否则 0。

## 5. changes.diff（trace 产物）

标准 unified diff（`difflib`，上下文 2 行），fromfile=baseline，tofile=revised；只含本轮真实改动。

## 6. 回复信块格式（templates/response_letter.md）

每条意见一个 `## 回复 <编号>` 块（verify 按此切分块做反驳合规核查）：

```
## 回复 R1.1
**感谢**：...
**立场**：采纳 / 部分采纳 / 不采纳（礼貌反驳）/ 澄清 / 无法执行
**修改说明**：动作 / 证据理由 / 替代方案 / 缓冲语（四槽位）
**修改位置**：章节/段落/行号，锚点：「修订稿原文片段（≥6字）」
**子要求逐条结论**：...
```
锚点行必须含「锚点」字样，引文用「」或 `` ` `` 包裹；引文须原样摘自修订稿（允许跨行）。

## 7. result.json（平台契约，字段名以实际 case.json 的 output_contract 为准）

必备：`case_id`、`status`（partial/complete/failed）、主结果路径、`sources`（逐条决策与证据/来源）、`uncertainty`（材料缺口与人工确认项）、`change_log`（修改记录）。见 `examples/minimal_example.md` 示意。

## 8. mapping_table.md（闭环映射表，格式见 templates/）

一行一个子要求：意见编号 | 子要求摘要 | 类型 | 严重度 | 处置级别 | 决策 | 修改动作 | 修订稿位置锚点 | 证据状态 | 备注/冲突；后附未到位证据清单（意见编号/所需证据/状态/原因/替代说明）。锚点与回复信、changes.diff 三者一致。
