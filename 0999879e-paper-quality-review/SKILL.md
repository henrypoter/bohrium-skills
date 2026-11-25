---
name: paper-quality-review
description: 论文质量审查。对实际稿件执行事实、引用、方法、统计、论证与规范六分面检查；输出精确到句且带原文逐字引文、SHA-256、依据、严重度和可执行修改的问题清单。适用于投稿前/审稿/结题材料质量审查，尤其需要引用—论断对照、跨章节核证和可复跑结果时。
---

# 论文质量审查：先绑定原文，再作判断

交付不是概括或泛泛评语，而是可交办、可逐条复核的 `result.json`。每条问题必须能回到实际原句；未读取、未获得依据和无法判断分别进入 `not_checked` / `needs_review`，不得写成“无问题”。不代写、不做查重、不替代编辑/同行评审。

## 1. 输入、输出与不可省略的现场读取

1. 实际读取 `/input/case.json`、`/input/task.md` 和 `environment/resources.yaml`；从 `case.json` 找到真实材料路径，并保留 **原始 `output_contract` 的全部字段与 `case_id`**。标签不能代替论文内容。
2. PDF 使用环境中实际可用的解析器处理原 PDF；不得假定存在预抽取文本。文本保存在 `/app/work/manuscript.txt`，解析器及异常写入版本/日志。文字定位以该 UTF-8 文本为准。
3. 最终写 `/app/output/result.json`，可另写 `issues.md`、`citations.json`、`gain.json`。所有结论基于本次运行，不复制示例或预生成正式答案。
4. 本 Skill 工具只依赖 Python 3 标准库。示例位于 `bench/fixtures/`，只用于说明接口和自测。

## 2. 可执行闭环（按顺序，失败立即如实降级）

### A. 锁定版本并建立句子坐标

```bash
cd /skills/weekly-skill
python3 scripts/review_tool.py index /app/work/manuscript.txt --out /app/work/index.json
python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' /path/to/original_input
```

`index.json` 给出 `source_sha256`、页码（form-feed）、行/段/句、Unicode 字符起止偏移和每句哈希。`manuscript_version` 同时记录原文件 SHA-256、抽取文本 SHA-256、解析器；原文件和抽取文本不能共用一个含义不明的哈希。

### B. 六个分面全部给出处置

| `checked_scope` 键 | 必查内容 | 判定所需证据 |
|-|-|-|
| `fact` | 跨摘要/正文/图表数值、单位、定义、事实 | 冲突双方的逐字 span；外部事实须有实际来源 |
| `citation` | 正文论断—引文—被引文献主张 | 本文论断 span + 被引来源 span；只匹配题录不等于支持 |
| `design` | 对照、样本量/抽样、随机化、盲法、混杂 | 方法 span + 受影响结论 span；区分设计缺陷/报告不全 |
| `statistics` | 检验适配、效应量、CI/误差、多重比较、重复 | 统计方法 span + 结果 span；不重算则不声称重算 |
| `argument` | 假设—证据—结论链、相关/因果、外推 | 证据句和结论句双 span，指名断裂环节 |
| `compliance` | 数据、伦理、利益冲突、图表来源、目标要求 | 声明/缺失检索范围 + 实际规范版本；不编造条款 |

每类只能取 `checked / partial / not_applicable / not_checked`。`checked` 要写 `search_scope`，其余写具体 `reason`。**没有问题数不等于没检查，发现问题数也不证明已检查。**

### C. 引用解析与逐条主张对照

```bash
python3 scripts/review_tool.py citations /app/work/manuscript.txt --out /app/work/citations.json
```

该命令解析数字方括号引文、展开区间、映射参考文献，并产生 `manuscript_claim + reference_entries + support:not_checked`。悬空的引文号给出精确定位和补条/改号动作。作者—年份引文需人工按同一结构补配；没有参考文献表时输出 partial，不猜 DOI、题名或结论。只有实际读到被引全文/允许证据摘录后，才能把 `support` 改为 `supported / contradicted / partial / unclear` 并形成确认问题。

### D. 形成可交办问题

每条 `issues[]` 必须包含：

- `category` 六类之一；`type=fact_error|insufficient_evidence|normative_issue|suggestion`，不得把四类混为“错误”。
- `severity=critical|major|minor`：核心结论/数据可信度受损为 critical；影响解释或合规且可补救为 major；局部格式/表达为 minor。严重度不随情绪或缺失资料自动升降。
- `status=confirmed|needs_review`。只有引文、定位、依据都能核验才 confirmed；被引全文不可得、表述多解等必须 needs_review。
- `location + quote + quote_sha256`：从 `index.json` 取原句或其连续子串，禁止拼接、 paraphrase、省略号拼接。`evidence[]` 第一项重复主 span，其他项提供冲突句/被引文献句。
- `basis[]`：可核对的规则或来源，含 `kind/source/locator/statement`；指南依据另含版本（及已获得的日期）。
- `fix={action,target,instruction,suggested_text?}`：target 指到待改句/节，instruction 写明增、删、改、核什么；禁止“注意”“建议检查”“请修改”这类空动作。

缺失项使用真实章节标题/首句作 `location` 锚点，同时填 `detection:"absence"` 与 `absence_evidence={searched:true,search_scope,source_sha256,expected,statement}`；锚点不是伪造的“缺失原文”。

### E. 三个硬闸，全部通过才可交付

```bash
python3 scripts/review_tool.py verify /app/output/result.json \
  --source manuscript_text=/app/work/manuscript.txt \
  [--source ref_1=/app/work/ref_1.txt]
python3 scripts/review_tool.py coverage /app/output/result.json
python3 scripts/review_tool.py schema /app/output/result.json
```

- `verify` 逐字检查 quote、起止偏移、页/行/段/句、源文件和 quote 的 SHA-256；有多个来源就逐一传入，**不传源文件不会静默通过**。重复问题也必须合并。
- `coverage` 检查六类处置及原因/范围，不用 issue 数冒充覆盖面。
- `schema` 检查版本、类型、证据、依据、可执行 fix、缺失检索和 gain。任一失败先修复再交付；无法修复则 `status=partial/failed` 并列 `unchecked`。

## 3. `result.json` 最小骨架（字段是必需，不是建议）

```json
{
  "result_schema_version": "2.0.0",
  "tool_version": "3.0.0",
  "case_id": "来自实际输入",
  "status": "pass|issues|partial|failed",
  "manuscript_version": {"file":"实际文件", "source_id":"manuscript_text", "file_sha256":"64位", "text_sha256":"64位", "extractor":"实际解析器/版本"},
  "issues": [{"id":"P1", "category":"argument", "type":"insufficient_evidence", "severity":"major", "status":"confirmed", "location":{}, "quote":"逐字原文", "quote_sha256":"64位", "claim":"证据链何处断裂", "evidence":[{}], "basis":[{}], "fix":{"action":"clarify","target":"s00001","instruction":"把结论限制到实际样本并补充限定语"}}],
  "checked_scope": {"fact":{"status":"checked","search_scope":"全文"}, "citation":{"status":"partial","reason":"缺被引全文"}, "design":{"status":"not_checked","reason":"尚未执行"}, "statistics":{"status":"not_applicable","reason":"纯理论研究且无统计检验"}, "argument":{"status":"checked","search_scope":"全文"}, "compliance":{"status":"not_checked","reason":"未提供目标规范"}},
  "gain": {"status":"not_measured", "reason":"平台未提供同输入基线和独立裁决"},
  "unchecked": [], "sources": [{"source_id":"manuscript_text","path_or_url":"实际路径","role":"manuscript","sha256":"64位"}],
  "uncertainty": [], "change_log": []
}
```

## 4. 同输入基础 Agent vs 本 Skill（只记录真实测量）

1. 平台提供/生成对照时，两臂使用相同 `case_id`、`manuscript_version.text_sha256`、允许资料、网络权限、模型预算和任务；保存各自真实 `runtime={elapsed_seconds,manual_review_seconds,rounds}`。
2. 独立逐条裁决 `decisions.json`：`baseline` / `skill` 分别为 `{issue_id:"supported|unsupported|unresolved"}`，并绑定 case、文本哈希、 `permissions`、`allowed_sources` 和预算。后三项必填且明确说明两臂共享条件；unresolved 不偷算为正确或错误。
3. 执行：

```bash
python3 scripts/review_tool.py compare /app/work/baseline.json /app/output/result.json \
  --decisions /app/work/decisions.json --out /app/work/gain.json
```

把真实 `gain.json` 内容并入 `result.json.gain`。它输出已裁决精度和误报率、两臂差值及实际耗时/人工核对/轮次差值；IDs 未裁决齐全、稿件哈希不同或共享权限/资料/预算未记录时会失败。没有真实基线时固定 `gain.status=not_measured` 并说明原因，禁止用 bench 数字冒充当次正式增益。

## 5. 异常处置表（识别信号 → 具体动作）

| 失败情形 | 识别信号 | 强制动作 |
|-|-|-|
| 稿件解析失败/缺页 | 读取非零退出、UTF-8 strict 失败、index 句数为空、页数/目录与输入说明不符 | 换用环境中另一实际解析器或 `-layout` 重试；仍失败的页列入 unchecked，相关分面 partial；全文不可读则 failed，不据残缺文本给确认结论 |
| 图表无法读取 | 正文引用图/表但图像缺失、渲染失败、坐标/文字不可辨 | 记录图表编号和已尝试方式；仅审查可读文字，相关数值/图像一致性子项 not_checked，不声称图表无冲突 |
| 参考文献缺失 | `citations` 报无文献表/悬空条目，或正文有引文而列表未提供 | citation 设 partial；题录真实性与语义支持 needs_review/not_checked；不补造元数据，不把缺失资料当违规 |
| 原文表述歧义 | 同一原句存在两种会改变判定的语法/指代读法 | 保留逐字句，分别列读法和各自影响，issue 设 needs_review，fix.action=clarify 交作者确认 |
| 稿件超长 | 分段预算不足、章节/句号未覆盖、运行时限逼近 | 以 index 的连续句号/章节分批；checked_scope 记录实际范围，未处理句号进 unchecked，最终 partial，禁止抽样后宣称全文审查 |
| 数据与结论冲突 | 两个真实 span 的数值/方向不一致，或结论超出数据范围 | 双 span 都进入 evidence；按对核心结论影响定严重度，给出重算/更正目标；无法判断哪个正确时 needs_review，不擅改数据 |
| 重复运行不一致 | 同输入哈希却 issue ID/定位变化 | 按 `(category,char_start,id)` 排序，重新 verify；保留 change_log，未复现条目不作 confirmed |

## 6. 自查与边界

```bash
python3 bench/bench_run.py
```

完整最小示例见 `bench/fixtures/good_result.json`（明确仅为 synthetic fixture）。本工具保证定位、字段和比较口径，不代替语义裁决；数字参考文献自动映射不覆盖作者—年份格式；外部事实、被引全文和图像不可读时必须保留边界。维护时修改规则/解析逻辑须升 `tool_version` 并更新 REVISION 与 bench。
