# 数据格式规范（可复用）与安装维护

本 Skill 的中间态与产物均为纯 JSON / Markdown，**无私有二进制格式、纯 Python 标准库**，
可被其它工具直接读取与复用。以下 schema 与提交版本（v5，成稿优先）一致，可用 `scripts/selftest.py`
的夹具输出对照验证。

## 1. 章节文件 `chapters/NN_标题.md`（骨架 → 正文，就地替换）

```markdown
# 第2章 研究方法

<!-- budget=600字 -->
> 任务：按task.md提纲撰写本章。数字/引用/图表只用材料；图N-M/表N-M先引后出连续；缩写首现全称（ABBR）；缺材料记【缺口】。

【占位：待写——只用给定材料，缺材料记【缺口】不编造】
【缺口：材料未见本章素材；需人工补充，禁编造】
```

- 文件名 `NN_标题.md`：两位序号为组装顺序的唯一依据；标题经 `[^\w一-鿿]+→_` 清洗、截 20 字符。
- 写作 = 用正文替换 `【占位…】` 行；`【缺口…】` 行可保留并在 result.json `gaps` 登记。
- 行内约定（一致性脚本据此判定）：
  - 图表：题注独立成行 `图N-M 说明` / `表N-M 说明`（行首可带 `**` 或 `>`），正文先引后出、按章连续；
  - 引用：数字 `[n]` / 范围 `[1-3]`（`[0,1]` 等数学区间自动豁免）；或键 `[@key]` + `@key{...}` 条目；或 `\cite{key}`/`\bibitem{key}`；
  - 缩写：首现 `全称（ABBR）`；
  - 文献条目：独立成行 `[n] 作者. 题名. 年.`（行首 `[数字]` 识别为条目）。

## 2. 提纲与规划 `plan.json`

```json
{"total_words": 3000, "min_total_words": 3000,
 "length_policy": "总字数>=min_total_words；每章>=min_words；禁占位/待补充/本章略",
 "outline_source": "task.md | default-thesis",
 "materials_scanned": 1,
 "chapters": [{"order": 1, "title": "绪论", "purpose": "按task.md提纲撰写本章",
               "word_budget": 600, "min_words": 600, "need_material": 1, "numbered": 1,
               "materials": ["/input/notes.md"], "gaps": [],
               "file": "chapters/01_绪论.md"}]}
```

- `outline_source=task.md` 表示从 task.md 解析到提纲（单行/多行/空行分隔均可，多行优先）；否则回退默认九章体系（摘要/绪论/文献综述/研究方法/结果与分析/讨论/结论与展望/参考文献/附录）。
- `materials` 为关键词匹配的材料映射（每文件取前 1500 字 head 参与匹配）；`gaps` 非空即「材料未见本章素材」。
- **篇幅纪律（成稿优先的核心）**：`min_words = max(600, word_budget×60%)`，参考文献/致谢/附录类为 `max(150, word_budget×50%)`；`min_total_words` 即题面字数（未明示取 30000）。`--assemble` 逐章计字数并打印 `LENGTH` 与 `SHORT <file>: 实际/下限`，**只提示、exit 恒 0**。

## 3. 一致性报告 `consistency.json`

```json
{"chapters": ["…/01_绪论.md"],
 "rules": ["cite-missing", "float-missing", "float-number", "term-abbr", "number-unsourced"],
 "rule_count": 5,
 "summary": {"issue": 1, "warn": 0, "info": 0},
 "advisory": true,
 "note": "advisory：只报告不阻断，不要求重写已完成章节；结果仅进 uncertainty。",
 "issues": [{"type": "cite-missing", "severity": "issue",
             "file": "…/01_绪论.md", "line": 3,
             "evidence": "引用[3]无条目", "suggestion": "补或删条目"}]}
```

- 退出码恒 0；`severity ∈ {issue, warn}`（`info` 保留兼容、当前不产出）；规则全集与判据见 SKILL.md §2 表（**5 条**：cite-missing / float-missing / float-number / term-abbr / number-unsourced）。
- 检查器**只报告**：不阻断导出、不触发返工；`--finalize` 只把 issues 追加进 `uncertainty`。
- `issues` 按 severity→文件→行号排序；每条带证据与修复建议，可直接被 `thesis.py --finalize --consistency` 并入 result.json `uncertainty`。

## 4. 改动留痕 `changes.jsonl`（一行一条）

```json
{"ts": "2026-11-16T00:00:00Z", "file": "chapters/03_结果.md", "rule": "number-unsourced",
 "before": "92.0%", "after": "88.5%", "reason": "与结果章一致（一行能改完才改）"}
```

由 `thesis.py --changelog --file … --rule … --before … --after … --reason …` 追加；支持「可回退、可比较、可说明」。

## 5. `result.json`（交付契约）

| 字段 | 说明 |
|-|-|
| `case_id` | 来自 `/input/case.json`（缺省 `unknown`） |
| `status` / `status_reason` | `success` / `partial` / `undeterminable` / `refused`，口径见 SKILL §3 |
| `deliverables` | 产物路径表（finalize 校验文件真实存在，缺失自动记 uncertainty） |
| `source_map` | `[{claim, source:"文件:行"}]`，覆盖数字/术语/引用/图表/论断 |
| `gaps` / `review_items` | 材料缺口 / 待人工确认项 |
| `sources` / `uncertainty` | 材料清单 / 不确定性（一致性 issue 自动并入） |
| output_contract 字段 | `--init` 时从 case.json 并入全部键，先置 null 再逐步回填 |

## 6. 安装

- 将本目录整体安装为 `/skills/weekly-skill`（平台自动完成）；本地复用：复制 `SKILL.md` + `scripts/` 到任意目录，从该目录执行 SKILL §1 命令。
- 依赖：Python 3.8+ 标准库（零 pip 安装）；pandoc / xelatex(+Noto Sans CJK SC) / soffice / pdftotext 为渲染与 PDF 抽取增强，缺失自动降级（仅 Markdown 直出），不阻断。

## 7. 篇幅上限与已知失败模式

- 篇幅上限：每章一次模型请求内完成，长章分节写；材料扫描每文件取前 1500 字；提纲最多 12 章；单次 `--consistency` 并入 uncertainty 最多 50 条。
- 篇幅下限：见 §2 `min_words`/`min_total_words`；未达标只提示（`SHORT`），不阻断导出——**成稿优先，不为凑字数重写已完成章节**。
- 已知失败模式：①提纲为极端自由格式时回退默认九章（plan.json `outline_source` 可查）；②材料映射为关键词启发式，可能漏配，需 P1 人工审阅；③缩写/数字规则为启发式，正向夹具（selftest）保证常见干净稿件零误杀；④中文 PDF 渲染依赖 xelatex+CJK 字体，缺失记 uncertainty。

## 8. 维护

- 版本：v5（2026-11-16，成稿优先重构）；演进与真实平台分（v1=56.0 / v2=50.0 / v3=67.0 / v4=67.0）见 SOLUTION.md。
- 自查与回归：`python3 scripts/selftest.py`（正向零误杀+变异 5 规则命中+篇幅纪律+5 类异常）、`python3 bench/bench_run.py`（公平对照）均须 exit=0 方可改版；改规则须同步 SKILL §2 表与本文件 §3。
- 问题反馈：改稿经验与失败教训沉淀于 SOLUTION.md，欢迎按同一夹具方法（先正向零误杀、再变异必命中）提交回归。

## 复用约定

- 消费方只需实现 §1 行内约定与 §3 报告结构，即可复算任一一致性结论。
- 新增 issue 类型时保持 `severity` 三档与字段不变，向后兼容读取。
