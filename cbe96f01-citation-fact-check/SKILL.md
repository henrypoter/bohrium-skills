---
name: citation-fact-check
description: 引用与事实核验：六类检查项分面审查、每条定位到原句并逐字核验、严重度分级、已查/未查范围显式
---

# 引用与事实核验

对一份稿件产出**可直接交办的问题清单**：每条有原文位置、原句引用、判断依据、严重度、修改建议。不是整篇评语，不复述内容。

不适用：代写、学术不端认定、期刊编辑决策。模型判定是**待作者确认的候选问题**，不替代编辑与同行评审。

## 调用

- 输入：`/input/case.json`、`/input/task.md`、稿件（PDF/MD/TXT）
- 输出：`/app/output/result.json` + 问题清单（CSV/MD）
- 工具：`scripts/review_tool.py`（`verify` / `summary` / `schema`）
- 模板：`templates/checklist.md`（六类检查项 + 判定锚点 + 严重度锚点）

## 工作流

### 0. 锁定稿件版本
先记录稿件版本（文件名 + 日期或哈希）到 `manuscript_version`。**版本不记录，后面所有定位都无法复核**。

### 1. 抽取正文并按检查项分面审查
按 `templates/checklist.md` 六类逐项过：
| 类目 | 查什么 |
|-|-|
| `fact` 事实核验 | 数据、数值、单位、常识性事实是否与稿件自述及公开事实一致 |
| `citation` 引用支持 | 被引文献是否真的支持该论断（不看"有没有引"，看"引的对不对"） |
| `design` 方法设计 | 对照、样本量、随机化、盲法、混杂控制是否足以支撑结论 |
| `statistics` 统计报告 | 检验方法是否匹配数据结构、是否报效应量与不确定性、是否多重比较校正 |
| `argument` 论证链 | 结论是否超出证据、是否存在因果化表述、有无未排除的替代解释 |
| `compliance` 学术规范 | 伦理审批、数据可得性、利益冲突、图像重复使用、作者贡献 |

**未涉及的类目也要在 `checked_scope.not_checked` 里写明**，不要静默跳过。

### 2. 每条问题定位到原句（这是误报控制的根本）
每条 issue 必须有：`location`（页/段/表/图号）、`quote`（**原文逐字片段**）、`claim`（问题是什么）、`fix`（怎么改）、`severity`。
- 引文必须**逐字**，不得改写、概括或拼接。
- 写完立刻跑一遍核验，把"原文里根本不存在"的引用揪出来：
```bash
python3 scripts/review_tool.py verify issues.json --text manuscript.txt
```
输出里的 `quote_not_in_source` 就是误报候选——必须回到原文确认，改引文或删条目。`duplicates` 是同一处被重复报的条目，合并。

### 3. 严重度分级（有锚点，不凭语气）
`critical`：结论不成立或数据不可信；`major`：影响可信度但有补救；`minor`：表述与格式。锚点见 `templates/checklist.md`。

### 4. 覆盖自检
```bash
python3 scripts/review_tool.py summary issues.json
```
看 `unchecked_categories`：确实是本文不涉及的，写进 `checked_scope.not_checked` 并给理由；不是，就补查。

### 5. 增益对照（不要只写自述）
同一稿件、同一检查项、同一预算，分别用基础 Agent（不加载本 Skill）与本 Skill 各跑一次，报：问题条数、经原文核验的命中率、误报率。差异要能指到具体条目。

### 6. 异常处置
| 异常 | 动作 |
|-|-|
| 稿件解析失败/乱码 | 换 `pdftotext -layout` 或按 UTF-8/GBK 重解一次；仍失败则标该段不可读，**不据残缺文本下判断** |
| 图表无法读取 | 记 `unchecked`，写明"图 N 不可读，相关结论未核" |
| 参考文献缺失 | 涉及引用支持的条目降级为 `major` 并注明"原文缺文献列表，未能核对" |
| 原文表述歧义 | 保留原文 + 写出两种读法，标 `minor`，交作者澄清 |
| 稿件超长 | 分面分段处理，在 `checked_scope` 写明已覆盖与未覆盖章节 |
| 数据与结论冲突 | 记为 `critical`，同时引结论句与数据句两处 quote |

### 7. 诚实输出
写 `result.json` 后自检：
```bash
python3 scripts/review_tool.py schema /app/output/result.json
```

## result.json 契约

```json
{
  "case_id": "", "status": "pass|issues|partial|failed",
  "manuscript_version": "v1.2 / 2026-11-20 / sha256:…",
  "issues": [{"id": "P1", "category": "fact|citation|design|statistics|argument|compliance",
              "severity": "critical|major|minor", "location": "结果 第2段",
              "quote": "原文逐字片段", "claim": "问题描述", "fix": "修改建议",
              "evidence": "判定依据（规范条目/文献/数据）"}],
  "checked_scope": {"did": ["..."], "not_checked": ["..."]},
  "gain": {"baseline_hit_rate": null, "skill_hit_rate": null, "false_positive_rate": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
不编造问题、不改写引文、不把"没查"说成"没问题"。每条问题都能让人翻到原句核对。

## 本课题聚焦
本题聚焦**引用支持与事实核验**。不查「有没有引用」，查「引的对不对」：被引文献是否支持该论断的方向、是否为二次转引、关键论断是否缺引用；同时核数值与单位在文内是否自洽。每条必须写出被引文献的实际结论与本文论断的差异。
