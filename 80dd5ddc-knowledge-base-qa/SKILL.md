---
name: knowledge-base-qa
description: 科研知识库问答：多文件检索、逐论断精确引用、版本去重与冲突处理、缺证判断、页段行回链及可复跑核验
---

# 科研知识库问答

在**给定资料库范围**内回答，不把通用常识伪装成库内事实。交付的不只是答案，还包括当前检索范围、每个关键论断的文件/内容版本/原文/页段行坐标、无依据问题的缺口和异常恢复记录。

不适用：绕过权限访问私人账户、在没有资料时凭印象作答、把词面匹配当作科学结论证明。文件不可读或扫描件未 OCR 时只能诚实降级。

## 判对硬约束（三道闸）

1. **逐论断回链**：每个关键论断至少一条证据，且 `path + 完整 sha256 + version + role + chunk_id + quote + locator` 全部与索引一致；`quote` 必须是目标段落原文的精确子串。文件变了、版本错了、页段行错了均不得通过。
2. **敢说没有，也敢说冲突**：`no_evidence` 必须列 `missing` 和实际 `search` 命令；矛盾证据分版本/文件并列，不能无依据选一个。索引异常全部进入 `exceptions`，不可静默跳过。
3. **第三人可复跑**：保存确定性 `index_sha256`、实际 `run.commands`、输入根、检索与排除范围、起止时间；最终 `qacheck` 通过。若 `status=pass`，不能有未解决异常；已标 `resolved` 的异常必须从原资料修复并重跑 index，不能只改状态文字。

任一闸不满足：修复或降为 `issues/partial/failed`，不能把部分回答写成全部完成。

## 输入、输出与工具

- 输入：`/input/case.json`、`/input/task.md`、实际资料文件及版本/管理说明；先读 `output_contract`，保留其中全部字段。
- 工作区：`/app/work`；最终：`/app/output/result.json`、`index.json`、必要的提取文本、检索与冲突证据记录。中间答案也尽早保存，避免超时丢失。
- 新工具：`scripts/qa_tool.py`（标准库，`index/search/qacheck`，版本 `1.0.0`）；原有 `scripts/file_tool.py` 可用于补充字节清单，但不能代替证据回链。
- 平台安装后 `SKILL_HOME=/skills/weekly-skill`；本地使用时设为提交目录。模型、预算、原生 trace 和平台增益不得自行编造。

```bash
export SKILL_HOME="${SKILL_HOME:-/skills/weekly-skill}"
mkdir -p /app/work /app/output
QA="$SKILL_HOME/scripts/qa_tool.py"
```

## 工作流

### 0. 先固定问题、范围和版本规则

逐题拆分用户问题中的关键论断，记录需要哪些字段/日期/版本。读取实际文件与管理说明，不根据错误领域标签补造内容。版本只按“内容 SHA-256 + 任务中的行政版本说明/修改时间”判断；文件名 `final` 不能单独决定 current。

### 1. 文本准备：不可读、PDF、扫描件先处置

- UTF-8 文本/Markdown/CSV/JSON/HTML 可直接索引；DOCX 由标准库读取 `word/document.xml`。坏编码报错后先确认原编码，禁止用替换字符伪造原文。
- PDF 先用环境**实际可用**的工具提取文本，保存为相对路径对应的 `<原文件>.txt` 侧车。若 `pdftotext` 可用，可执行 `pdftotext -layout input.pdf /app/work/text/input.pdf.txt`；页间保留 form feed。记录真实工具、版本和命令，不可用时不声称已运行。
- 扫描件或提取为空时，只有实际可用的 OCR 才能补文本；OCR 后须抽样核对数字、表格和页界。无 OCR/仍为空就标 `scanned_no_text`，不猜内容。
- 坐标约定：普通文本为提取文本的段落和起止行；PDF 页码只来自带 form feed 的提取侧车，否则 `page=null`，不得猜页码。

### 2. 建索引并处理重复/版本

有明确版本说明时写 `versions.json`：

```json
{
  "chains": {"report": {"current": "docs/report_v2.txt", "history": ["docs/report_v1.txt"]}},
  "file_versions": {"notes.txt": "snapshot-2026"}
}
```

然后执行：

```bash
python3 "$QA" index /app/work/library --versions /app/work/versions.json \
  --text-dir /app/work/text --output /app/output/index.json
```

没有提取侧车或版本文件时省略对应参数。索引包含：

- 文件路径、类型、大小、权限、来源路径、完整哈希、mtime、提取方法与文本来源；
- 重复组（同内容副本不默认重复召回）；
- 候选版本（同 base 且不同哈希）和显式 `current/history/supersedes`；
- 每段的 `doc_id/chunk_id/quote/文本哈希/page/paragraph/start_line/end_line`；
- 文件不可读、空目录、空文件、无文本、版本冲突等 `anomalies`。

**默认检索只含 `include_in_search=true` 的 current canonical 文档**，history/duplicate 不悄悄混入；回答历史比较时才显式 `--include-history`。未声明版本的不同内容会报 `version_conflict`，不是自动选 mtime 最新。

`index` 在完全不可检索时非零退出；部分可检索但有异常时产出索引并标 `issues`，只能回答已覆盖部分。任何 anomaly 必须在最终 `exceptions` 中有同 `type/path` 的记录；若仍在索引中，不能标 `resolved`。

### 3. 多查询检索，保留真实范围

```bash
python3 "$QA" search /app/output/index.json --query "设置温度" --limit 8 \
  > /app/work/search-temperature.json
# 仅当问题涉及旧版本差异：
python3 "$QA" search /app/output/index.json --query "设置温度" --include-history
```

每个问题至少用关键实体/指标检索；必要时再用同义词、英文缩写和 `--path` 做限定检索，记录所有实际命令。返回 hit 已带 `path/sha256/version/role/chunk_id/locator/quote`，可作为引用骨架。

- 先读完整命中段落和邻近上下文，再作答；不要只抄搜索词周围几个字。
- `no_evidence` 表示**当前词面检索无命中**，并不自动证明语义上不存在。须换关键词并检查相关已读段落/范围后才能写“库内没有依据”；仍不确定时写“当前索引未检出”，列出未读/不可读范围。
- 版本冲突未解决时分别检索和引用各版本，不能合并成貌似统一的答案。

### 4. 写答案：一论断一证据组

答案状态只用：

| answer.status | 使用条件 |
|-|-|
| `answered` | 所有关键论断有证据；每条 claim 有 `claim_id/text/evidence[]` |
| `no_evidence` | 没有可支持答案的库内证据；`claims=[]`，`missing[]` 指明需要什么文件/字段/版本 |
| `partial` | 一部分有证据、另一部分缺失；claims 回链，同时写 `missing[]` |
| `conflict` | 证据不一致；分文件/版本陈述，顶层 `conflicts[]` 至少给两条不同锚点 |

引用字段完整复制检索回链，**quote 不翻译、不改写、不跨段拼接**。回答中的概括/计算若基于多条原文，把多条证据都挂到同一 claim，并在文字中说明计算关系；字符串坐标核验不代替论断-原文语义蕴含人工复核。

证据互相矛盾时：`conflicts[]` 写 `topic/status/explanation/evidence`。默认 `unresolved`；只有存在独立校准、行政版本决定或可核验更正时才 `resolved`，并写 `resolution`。优先最新文件不是独立依据。

### 5. 异常处置与恢复（不得静默跳过）

| 异常 | 识别与即时动作 | 恢复、答案边界与状态 |
|-|-|-|
| 文件不可读/编码错误/DOCX 损坏 | index 标 `file_unreadable/text_decode_error`，记录路径、错误；排除出已检索范围 | 授权、修复或重取后重跑 index；未读部分写 missing，整体 partial/issues |
| 扫描件无文本 | 空侧车/PDF 无文本标 `scanned_no_text`，不得当普通空文档 | 实际 OCR 后核对并重建；无 OCR 则说明缺可检索正文，不猜答案 |
| PDF 尚无提取文本 | `text_extraction_required`，不直接读二进制猜词 | 用可用工具生成有来源侧车；工具不可用时 blocked |
| 权限不足 | 标 blocked，保留所需权限和路径 | 获得授权后重跑；受权限限制的范围列入 scope.excluded_documents |
| 目录为空 | `directory_empty`，完全不可检索时 index 失败 | 确认挂载/资料是否缺失；不生成无引用的事实答案，result 为 failed/partial |
| 空文件/空文本 | 区分真实占位与漏采，标异常 | 向提供方补件；仍空时写 missing，不把“无文本”当“问题没有答案” |
| 版本冲突 | 同 base 不同哈希报 `version_conflict`，不静默选 final/mtime | 有行政说明则写 versions 并重建；否则分版本并列，exception 保持 open |
| 证据互相矛盾 | 至少两条不同锚点进入 conflicts | 并列原文、版本和不确定性；无独立依据时 unresolved |
| 重复副本 | 完整哈希相同，只留 canonical 默认检索 | 副本仍可显式回链，标 `role=duplicate/duplicate_of`，不充作独立佐证 |
| 索引/文件哈希变化 | qacheck 拒绝指纹不符、错版本和错坐标 | 从原资料重新 index/search，更新所有引用，禁止手改哈希过关 |

### 6. result.json 契约与最终机检

保留原 `output_contract`，至少补以下结构。下面是**合成接口示例**，不是正式案例答案：

```json
{
  "case_id": "example-qa",
  "status": "pass",
  "scope": {
    "index_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "searched_documents": ["docs/report_v2.txt"],
    "excluded_documents": ["docs/report_v1.txt"],
    "include_history": false
  },
  "answers": [{
    "question": "示例：设置温度是多少？",
    "answer": "v2 记录为 42 °C。",
    "status": "answered",
    "claims": [{
      "claim_id": "c1", "text": "v2 记录设置温度为 42 °C。",
      "evidence": [{
        "path": "docs/report_v2.txt",
        "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "version": "v2", "role": "current", "chunk_id": "doc-bbbbbbbbbbbbbbbb:p0001",
        "quote": "实验设置温度为 42 °C。",
        "locator": {"page": null, "paragraph": 1, "start_line": 1, "end_line": 1}
      }]
    }]
  }],
  "exceptions": [],
  "conflicts": [],
  "run": {
    "tool_version": "1.0.0",
    "commands": ["index /app/work/library --versions /app/work/versions.json", "search /app/output/index.json --query 设置温度"],
    "input_root": "/app/work/library",
    "started_at": "2026-01-02T03:00:00Z", "completed_at": "2026-01-02T03:05:00Z"
  },
  "sources": ["/app/output/index.json"],
  "uncertainty": [],
  "change_log": ["仅示例；实际提交须由检索结果替换所有示例值"],
  "gain": {"baseline_citation_pass_rate": null, "skill_citation_pass_rate": null, "manual_lookups_saved": null}
}
```

`searched_documents/excluded_documents` 必须都是索引内真实路径。对于无依据回答，`run.commands` 要有实际 `search`；对于每个索引异常，`exceptions[]` 写 `type/path/status/action/recovery`。存在 unresolved 科学冲突可表示回答任务已完成，但仍须在 uncertainty 明确其结论边界；若资料范围未覆盖则整体不能 pass。

```bash
python3 "$QA" qacheck /app/output/result.json --index /app/output/index.json
python3 "$SKILL_HOME/bench/qa_bench.py"  # 开发自测，不是平台成绩
```

`qacheck` 核验完整 index 指纹、版本/角色、原文精确子串、页段行、每论断证据、no_evidence 缺证说明与搜索记录、冲突双锚点、异常闭环和检索范围。失败时保留真实中间产物，修复后从原资料重跑；不得编造缺失软件状态或科学数据。

## 最小调用示例

```bash
python3 scripts/qa_tool.py index ./library --output ./index.json
python3 scripts/qa_tool.py search ./index.json --query "示例指标"
python3 scripts/qa_tool.py qacheck ./result.json --index ./index.json
```

示意输出：`search` 返回 `status=ok` 的 hits，或 `status=no_evidence + missing`；均为接口说明而非正式案例结果。

## 边界与底线

工具是 UTF-8/Office XML 文本索引与坐标验证器，不是完整 PDF/OCR 引擎，也不证明论断与引文在科学语义上等价。复杂 PDF 必须借助实际可用提取/OCR；语义蕴含、表格计算和证据冲突仍需逐条核对。**不引用不可读文件、不混用历史与当前版本、不把词面零命中直接扩写成绝对不存在、不在缺证时编造。**
