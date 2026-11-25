---
name: logic-argument-review
description: 论文逻辑与论证审查：主张抽取(区分作者/引用/假设)、证据支撑核查、推理链完整性、章节衔接一致性、严重度分级+可执行修改建议，每条问题定位到句、引文逐字、建议可落地
---

# 论文逻辑与论证审查

对稿件做**逻辑与论证**专项审查：把作者主张抽出来逐条核查，看证据是否撑得住、推理是否跳步、前后是否自洽，产出一条能落到具体句子、可直接核对的问题清单。

**不适用**：事实/数值/统计/学术规范等非逻辑类审查、代写、学术不端认定。判定是待作者确认的候选问题，不替代编辑决策。

## 判对三件事（本题评分核心，不看报了多少条）

1. **问题真实存在，能回到原文某一句话**——`quote` 必须逐字，`verify` 核验。
2. **定位精确到句/段**——不能只给"第三章""讨论部分"，必须到第几段第几句。
3. **修改建议可执行**——说清"补什么证据 / 改哪句表述 / 把哪个结论降成什么强度"，不是"加强论证"。

三件事各有一条机检闸，跑完才能交：
```bash
python3 scripts/review_tool.py logic_check issues.json --text manuscript.txt
```

## 调用
- 输入：`/input/case.json`、`/input/task.md`、稿件（PDF/MD/TXT）
- 输出：`/app/output/result.json` + 问题清单
- 工具：`scripts/review_tool.py`（`logic_check` / `verify` / `schema`）
- 模板：`templates/checklist.md`

## 工作流（五个方向逐一过）

### 0. 锁定稿件版本
记录 `manuscript_version`（文件名 + 哈希/日期），否则定位无法复核。

### 1. 论点与主张抽取（方向1）
从摘要、引言、结果、讨论抽出核心主张，每条标注 `claim_type`：
- `author_claim` 作者自己的主张
- `cited_claim` 引用他人观点
- `hypothesis` 假设情形
- 保留限定条件（"可能""在X条件下""与Y相关"），不把弱表述拔成强主张。

### 2. 证据支撑核查（方向2）
对每条 author_claim 检查：支撑证据是否存在、来自本文实验还是所引文献、是否足以支撑该强度表述。重点抓两类：**结论超出数据**、**引用不支持观点**（引文说的和本文用它证明的不是一回事）。

### 3. 推理链完整性（方向3）
查前提→结论的跳跃：隐含假设未说明、替代解释未排除、相关当因果、循环论证。

### 4. 章节衔接与前后一致性（方向4）
引言承诺的问题是否在方法/结果里交付、方法与结果口径是否一致、摘要与正文结论是否一致、图表与正文描述是否对应。

### 5. 严重度与修改建议（方向5）
- 严重度有依据：`critical` 影响主结论或不可信 / `major` 有补救 / `minor` 表述问题。
- `fix` 落到具体句子：补什么证据、改哪句表述、降哪个结论强度，不写"加强论证""完善逻辑"这类空话。

### 6. 增益对照
同稿件同预算，基础 Agent vs 本 Skill 各跑一次，报：经原文核验的命中率、误报率、定位精确率。

### 7. 异常处置
| 异常 | 动作 |
|-|-|
| 论文解析失败 | 换 `pdftotext -layout` 或重解编码，仍失败标该段不可读，不据残缺文本下判断 |
| 扫描版无文本层 | 说明需 OCR 及置信度，低置信处标 `unknown`，不臆造引文 |
| 超长截断 | 分面分段处理，在 `checked_scope` 写明已覆盖/未覆盖章节 |
| 引用无法获取 | 涉及引用的条目降级 `major` 并注明"文献不可得，未能核对" |
| 章节缺失 | 标 `unchecked`，写明缺哪章，相关论断未核 |

### 8. 诚实输出
```bash
python3 scripts/review_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{
  "case_id": "", "status": "pass|issues|partial|failed",
  "manuscript_version": "v1.2 / 2026-11-20 / sha256:…",
  "issues": [{"id": "P1", "category": "argument",
              "claim_type": "author_claim|cited_claim|hypothesis",
              "severity": "critical|major|minor",
              "location": "结果 第2段 第3句",
              "quote": "原文逐字片段",
              "claim": "问题是什么", "fix": "补什么证据/改哪句/降什么强度",
              "evidence": "判定依据"}],
  "checked_scope": {"did": ["主张抽取","证据核查","推理链","前后一致"], "not_checked": []},
  "gain": {"baseline_hit_rate": null, "skill_hit_rate": null, "false_positive_rate": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
问题必须回到原句、定位到句、建议落到句。不编造、不改写引文、不把"没查"说成"没问题"。
