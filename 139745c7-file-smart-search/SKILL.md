---
name: research-file-retrieval
description: 科研文件智能检索。用于在本地/已挂载科研资料库中跨文件查找方法、配方、图表与数据关系，按项目/年份/批次/版本/权限等硬条件过滤，定位到 PDF 页与段落、Office 幻灯片或表格行，并交付可逐字复核的证据回链、版本/副本关系、失败恢复与公平增益记录。不用于开放网络检索、综述写作或权限系统建设。
---

# 科研文件智能检索：找到那一段，并让别人复核到同一段

核心不是文件名搜索，也不是返回整篇文件。必须完成：
**真实盘点 → 原文块索引 → 语义/同义扩展 → 全维度硬过滤 → 章节/页/段落定位 → 逐字回链机检 → 失败与版本关系交付**。

## 触发与边界

适用于“这个体系在哪个项目做过”“配方写在哪一版”“哪张图对应哪组数据”等已在库文件的问题。输入通常为 `/input/case.json`、`/input/task.md` 和已授权材料；实际路径以案例为准，不能假定存在本包 fixtures。

不做开放网络文献检索、论文综述、科学事实臆测、存储权限建设。扫描件未 OCR、加密/损坏或无权限文件不能当成已读；不依据文件名补造年份、项目、配方、图数关系或“当前版本”。

## 运行契约与资源

- 工作目录 `/app/work`；可编辑交付物与最终 `result.json` 放 `/app/output`。
- 平台安装后工具为 `/skills/weekly-skill/scripts/file_tool.py`；若实际安装根不同，以加载后的 Skill 根为准。
- 模板：`templates/result_template.json`、`templates/directory_spec.md`、`templates/aliases.example.json`、`templates/filters.example.json`。
- Python 3，无 pip 依赖。PDF 文本层优先调用系统 `pdftotext`；图片 OCR 只有显式 `--ocr` 且系统有 `tesseract` 时执行。OOXML 直接由标准库解析。
- **先读 `case.json` 的原始 `output_contract` 和 `task.md`。最终保留其中全部原字段及 `case_id`，再补充本流程字段；不可用模板覆盖原契约。**

## 0. 先读工单，建立问题—条件矩阵

1. 读取实际工单，列出每个问题的 `question`、所需关键文件/章节、答案粒度（段/行/图注/幻灯片）和完成标准。
2. 把年份、项目编号、文件类型、实验批次、版本、权限等全部写成结构化 `filters`。所有条件默认 **AND**；不得因结果少而删除、放宽或把硬条件改成语义词。
3. 记录输入文件根、元数据来源、管理版本说明、别名表、允许访问范围。权限不足与“没有命中”分开。
4. 只有案例明确授权时，才可从目录或文件名提取元数据；否则标 `unknown`。`final/latest/最新` 不是当前版本证据。
5. 尽早写 honest partial `result.json`，再增量完善；900 秒预算内优先保全已验证证据。

## 1. 盘点实际文件与权限

```bash
SKILL_DIR=/skills/weekly-skill
python3 "$SKILL_DIR/scripts/file_tool.py" inventory "$LIBRARY" \
  --output /app/work/inventory.json > /app/work/inventory.stdout.json
```

逐一登记路径、大小、完整 SHA-256、类型、可读状态。`duplicate_groups` 仅合并**同内容哈希**，副本只算一个独立证据但保留全部路径；同名不同内容不自动去重。软链不跟随，空文件、读取失败和失效路径均显式记录。

## 2. 建章节级索引，不猜缺失内容

将案例给定的元数据整理成 JSON/CSV（至少 `path`，以及真实存在的 `year/project/type/batch/version/permission/current/version_group/supersedes`）。字段定义见 `templates/directory_spec.md`。

```bash
python3 "$SKILL_DIR/scripts/file_tool.py" index "$LIBRARY" \
  --metadata /app/work/metadata.json \
  --aliases /app/work/aliases.json \
  --output /app/work/index.json > /app/work/index.stdout.json
```

无别名文件时可省略 `--aliases`。内置通用科研同义组只用于召回；案例词表优先，新增别名须记录来源，不能扩展过滤值。

索引覆盖：

- PDF：物理页 `page`、可识别的印刷页 `printed_page`、章节、页内段落；图注/表格块与跨页续块。
- DOCX：标题样式/编号章节、段落、表格行、页眉页脚/脚注；无稳定渲染页码时不编造。
- PPTX：幻灯片号、形状与段落、备注；XLSX/CSV：工作表、行号、单元格/字段。
- TXT/Markdown 等：标题层级与段落。

`version_candidates` 只是候选组；只有管理元数据 `current/supersedes/superseded_by` 等明确声明才形成 `version_groups`。同哈希副本、旧版和独立版本不得混作多份独立证据。

**先检查 `files[].status`、`warnings`、`metadata_errors`。** 修复可恢复问题后重建索引；无法修复的进入 `failures/skipped/recovery`，而不是留空后声称完成。

## 3. 每个问题单独检索，执行全部硬过滤

```bash
python3 "$SKILL_DIR/scripts/file_tool.py" search /app/work/index.json \
  --query '缓冲液配方写在哪一版' \
  --filters /app/work/filters-q1.json \
  --limit 20 --output /app/work/search-q1.json > /app/work/search-q1.stdout.json
```

过滤示例：

```json
{"year": 2024, "project": "P1", "type": ["pdf", "docx"],
 "batch": "B-7", "version": "v2", "permission": "read"}
```

支持标量等值、数组任一值、`eq/ne/in/contains/gte/lte/gt/lt/regex/exists` 与 `$and`；不支持的算子报错/排除，绝不静默忽略。缺过滤字段的文件会被排除并进入 `coverage_gaps`，这与“语义无匹配”区分报告。

检查 `semantic_expansions` 是否覆盖同义表述、缩写、跨语言和上下位词；检查 `search_trace.eligible_files_after_filters` 是否覆盖所有合格文件。不要只取分数最高者：按问题所需关键文件与章节逐一复核，并打开块前后文确认它确实回答了问题。

## 4. 证据回链必须逐字、定位到块

每条命中保留工具返回的：

- `path`、完整 `sha256`、`version`、`block_id`；
- `locator`：章节、PDF 物理页/印刷页/段落，或 DOCX 段落、PPTX 幻灯片、XLSX 工作表与行；
- `paragraph_first_sentence`、`quote`（该原文块的**逐字子串**，不润色、不翻译、不改空格）；
- `source_uri`、`duplicate_of/duplicate_aliases/independent_evidence_id`。

结论与证据一一对应。图与数据的对应关系只有在原文、元数据或明确标识支持时才能建立；否则写 `uncertainty`。跨页表格分别引用续块；双栏 PDF 若阅读顺序可疑，须对照原页渲染/文本层并降低状态，不能拼接成“新原文”。

```bash
python3 "$SKILL_DIR/scripts/file_tool.py" verify /app/work/search-q1.json \
  --index /app/work/index.json --root "$LIBRARY"
python3 "$SKILL_DIR/scripts/file_tool.py" verify /app/output/result.json \
  --index /app/work/index.json --root "$LIBRARY"
```

`verify` 会重算路径、块、版本哈希、逐字引文、全部定位字段和硬过滤，并检查当前文件是否变更是失效。失败就修正证据或重建索引，**不得关闭校验**。

## 5. 结构化交付与最终机检

以 `templates/result_template.json` 为补充骨架，合并原始 `output_contract`。至少保留：

- `inventory/files`：每个输入文件一行及真实状态；
- `queries[]`：`question/filters/hits/search_trace`，空结果另有 `no_hit.reason/action`；
- `version_groups`：关系及 `evidence`，无证据只报候选与不确定性；
- `operations/change_log`：实际命令、来源、索引/文件哈希、变更与恢复方式；
- `skipped/failures/conflicts/recovery/unchecked/sources/uncertainty`；
- `gain`：实测或 `platform_pending`，不虚构基础 Agent 分数。

状态：`pass`=契约范围内完整且无未决失败；`issues`=主任务完成但有副本/版本/非关键解析警告；`partial`=部分问题或文件未完成；`failed`=无法形成有效检索。空结果不是自动 `failed`，但必须有完整轨迹、过滤覆盖和恢复动作。

```bash
python3 "$SKILL_DIR/scripts/file_tool.py" schema /app/output/result.json \
  --index /app/work/index.json --root "$LIBRARY"
```

只有 `verify` 与 `schema` 均 `ok=true` 才可称机检通过；若原始契约另有字段，仍须另行逐字段核对。

## 6. 同输入同权限的增益对照

若平台提供基础 Agent 的真实输出，记录相同 `case_id/input_fingerprint/permissions_fingerprint`，再运行：

```bash
python3 "$SKILL_DIR/scripts/file_tool.py" compare \
  --baseline /app/work/baseline.json --skill /app/output/result.json \
  --index /app/work/index.json --gold /app/work/gold.json \
  --output /app/work/gain.json
```

`--gold` 仅在组织方提供时使用。比较有效证据率/数、金标准精确率与召回率、实际耗时；将真实输出复制进 `gain`，附公平性指纹。没有基础 Agent 输出时写 `{"comparison_status":"platform_pending"}`，不得自演基础 Agent 或编造提升。

## 异常识别与处置表

| 情形 | 识别信号 | 具体动作 |
|-|-|-|
| 无权限 | `permission_denied/readable=false` | 标 `blocked`，记录路径与所需只读权限；申请后重跑，不计入已检索覆盖 |
| 加密 PDF | `status=encrypted` 或密码错误 | 不用文件名猜内容；获得授权密码/解密副本后重索引，保留原哈希 |
| 损坏/解析失败 | `corrupt_or_unreadable/extraction_timeout` | 保留原件与错误，重新采集/分批解析；标 partial，不伪造引文 |
| 无文本层扫描件/图片 | `needs_ocr` | 经授权使用 `--ocr`；OCR 块标 `ocr_needs_review`，对照图像逐字复核，无 OCR 则明确未覆盖 |
| 重名文件 | 路径/文件名相同但哈希不同 | 不覆盖、不去重；保留两个哈希，结合元数据判版本，冲突入 `conflicts` |
| 改名副本 | 不同路径同 SHA-256 | 记 `duplicate_of/aliases`，只算一个独立证据，仍保留可点击副本路径 |
| 路径失效/挂载断开 | `path_invalid` 或 verify 当前路径失效 | 检查挂载、大小写和路径映射；恢复后重建索引，旧索引不冒充当前结果 |
| 索引后文件变化 | 当前 SHA-256 与索引不符 | 作废旧证据并重建；不可只改 result 中哈希 |
| 旧版 Office/未知格式 | `legacy_office_unsupported/unsupported` | 登记并授权转换为 OOXML；记录来源哈希、转换器和目标哈希 |
| 空结果 | `no_semantic_or_lexical_match` | 核对同义词、章节块与解析状态；可扩大语义召回但不得放宽硬过滤 |
| 条件排除全部 | `filters_excluded_all/coverage_gaps` | 补真实元数据或向用户报告条件无满足项；不擅自删条件 |
| 元数据冲突/缺失 | `metadata_errors` 或字段为 null | 列字段和冲突来源；标 unknown/待确认，不根据领域标签补造 |
| 印刷页≠物理页 | 两者字段不同 | 两者同时交付，PDF 链接使用物理页；不把印刷页当数组页号 |
| 双栏/跨页表格 | 块顺序异常或 `continuation_of` | 对照原页，引用各续块；顺序未确认则标 uncertainty |
| 版本无法唯一确定 | 多个 current、无 current 或关系冲突 | 不选 `final` 猜测；给候选、证据和恢复方式，必要时标 partial |

## 不适用与维护

本工具是词汇/配置同义组 + 字段约束 + 原文块证据的可审计轻量方案，不声称神经语义全覆盖；专业别名需按案例维护。PDF 复杂字体、手写扫描件、旧版 Office 和无权限内容可能需外部授权工具。维护时修改别名/解析/定位规则后，必须运行：

```bash
python3 /skills/weekly-skill/bench/bench_run.py
```

当前自测为 **51/51**（合成库，不是平台正式成绩），覆盖六个命令的正向零误杀与变异必命中。
