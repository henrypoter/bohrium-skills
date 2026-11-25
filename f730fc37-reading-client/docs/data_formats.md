# 数据格式规范（可复用）

本 Skill 的中间态与产物均为纯 JSON / Markdown，**无私有二进制格式**，可被其它工具直接读取与复用。
`annotations.json` 遵循 W3C Web Annotation Data Model（`TextQuoteSelector`），可被支持该标准的
标注工具（如 Hypothesis 系工具、Zotero 插件生态）消费。

## 1. `session.json`（会话状态，可跨会话续读）

| 字段 | 类型 | 说明 |
|-|-|-|
| `schema_version` | int | 当前为 `3`；字段变更时自增 |
| `tool_version` | str | 当前客户端为 `5.0.0` |
| `material_version` | obj\|null | `{path, bytes, sha256, format}`；读取失败时 hash 可为 null |
| `last_open_error` | obj\|null | encrypted_pdf/oversized_file/extract_timeout 等结构化失败及接管建议 |
| `doc` | str | 材料绝对路径 |
| `pages` | int | 页数 |
| `text_status` | str | `ok` / `no_text_layer` |
| `extraction` | str | `pdftotext-layout` / `pdftotext-raw` / `plain-text` |
| `page_offset` | int | 物理页 → 印刷页偏移 |
| `selection` | obj\|null | 当前选区锚点（结构见 §3） |
| `qa` | array | 问答记录；含 answer_id/answer_sha256/document_sha256/selection_sha256 与 evidence 数组 |
| `notes` | array | 批注记录 |
| `reading_position` | obj\|null | 断点：`{doc, physical_page, line, quote, source, ts}` |
| `opened_at` | int | Unix 时间戳 |

写入采用「临时文件 + `os.replace` 原子替换」，首次写入前自动生成 `.bak` 备份；读取时依次尝试
主文件、`.bak`，均失败则以 `fresh_after_corruption` 新建空会话。

## 2. `pages.jsonl`（逐页文本，一行一页）

```json
{"page": 1, "text": "该页全部文本…"}
```

行号即 `text.splitlines()` 的下标（从 1 起），是锚点里 `line` 的定义基准。

## 3. 锚点（anchor）三段式

```json
{"physical_page": 1, "line": 5, "prefix": "前文…", "exact": "被选原文", "suffix": "后文…",
 "confidence": "verbatim|normalized|fuzzy(0.92)|page_line_only"}
```

- `confidence` ∈ {`verbatim`, `normalized`, `fuzzy(...)`, `page_line_only`}；前两级视为**已核验**。
- `normalized` 含两个等价通道：空白折叠、以及**去全部空白后的精确比对**（解决中文 PDF 跨行断句）。
- `prefix` / `suffix` 各取约 48 字符，用于在文本轻微漂移时重新定位。

## 4. `annotations.json`（W3C Web Annotation）

```json
{"schema_version": 3, "tool_version": "5.0.0", "doc": "…",
 "material_version": {"path": "…", "bytes": 1234, "sha256": "…", "format": "text"},
 "annotations": [{"id": "qa1-ev1", "type": "Annotation",
   "body": {"question": "…", "answer": "…", "answer_id": "qa1"},
   "answer_sha256": "…",
   "target": {"source": "…",
     "selector": {"type": "TextQuoteSelector", "prefix": "…", "exact": "…", "suffix": "…"},
     "physical_page": 1, "line": 4},
   "confidence": "verbatim", "verified": true, "needs_confirmation": false}]}
```

批注（`type: Annotation`，`body.text`）与问答证据（`id` 前缀 `qa<N>-ev<M>`）共用同一结构，
因此可被同一批工具统一渲染、检索与再编辑。

## 5. `result_draft.json` / `result.json`

`export` 产出 `result_draft.json`，随后把题目 `output_contract` 字段合并为最终 `result.json`：

| 字段 | 说明 |
|-|-|
| `schema_version` / `tool_version` / `run_id` | `result.json` 结构、客户端版本和本次运行标识 |
| `material_version` / `artifact_manifest` | 原文身份与路径/字节数/SHA-256；其余交付文件摘要 |
| `case_id` | 来自 `case.json`；`export --case` 自动终稿并保留 output_contract 键 |
| `status` | `success` / `partial` / `unanswerable_from_material` / `failed` |
| `answers[]` | `{answer_id, answer_sha256, document_sha256, selection_sha256, question, answer, evidence:[{evidence_id, answer_id, document_sha256, quote, location, verified, confidence, needs_confirmation, anchor}]}` |
| `sources` | 材料清单 |
| `uncertainty` | 缺口与原因 |
| `needs_confirmation` | 需人工复核项清单 |
| `change_log` | 操作与取舍留痕 |

## 6. `reading_record.md`（人读版）

按「Q → 答案 → 证据锚点（页:行 + 置信度）→ 批注」顺序排版，供人工快速复核；与
`annotations.json` 一一对应，二者可交叉验证。

## 复用约定

- 消费方只需实现 §2/§3 两个最小结构（逐页文本 + 三段式锚点）即可复算任一答案是否可追溯到原文。
- `schema_version` 变更时保持向后兼容读取；新增字段不影响旧消费方。
