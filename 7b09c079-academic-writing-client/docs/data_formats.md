# 数据格式（data_formats）

会话状态与全部产物均为 **UTF-8 JSON / Markdown / 标准 OOXML（docx 为 zip 包）**，无私有二进制格式，第三方工具可直接读取复用。路径：`$AWC_ROOT`（默认 `/app/work/awc`）、`$AWC_OUT`（默认 `/app/output`）。

## 会话状态（$AWC_ROOT）

### project.json — 会话主状态

```json
{
  "case_id": "b1", "title": "综述修改示例",
  "created": "2026-11-16T06:00:00Z", "updated": "...", 
  "phase": "ingested | revised | verified | exported | resulted",
  "chapters": [{"id": "ch1", "title": "方法", "version": 3, "path": ".../chapters/ch1.md"}],
  "next_rev": 4,
  "gaps": [{"chapter": "ch2", "issue": "material file missing | material file empty", "path": "..."}]
}
```

- `phase` 即状态机当前阶段；全部写盘经「临时文件 + `os.replace`」原子替换，崩溃不产生半写状态。
- 损坏诊断：非法 JSON 或缺必填字段（chapters/next_rev/gaps/case_id）→ 明确报错退出码 1。

### chapters/<id>.md — 章节当前稿（可编辑 Markdown）

### history/<id>.v<n>.md — 版本谱系

每次 `revise` 前把当前章内容存为 `v<n>`（n 为改版前版本号），配合 `revisions.json` 的 version_in/version_out 可逐版回退比对。

### revisions.json — 修订记录（逐条可处置）

```json
[{"id": 1, "chapter": "ch1", "type": "revise|polish|format",
  "before": "<原文锚点>", "after": "<改后>", "reason": "<指令编号/依据>",
  "source": "<来源定位>", "status": "proposed|accepted|rejected",
  "version_in": 1, "version_out": 2, "anchor_count": 1, "ts": "...", "decided_ts": "..."}]
```

### claims.json — 论断-证据绑定

```json
[{"id": "C1", "claim": "准确率 88.1%", "evidence": "88.1%",
  "source": "b1.md", "locator": "ch1", "status": "bound|needs-human",
  "verify": "verbatim in b1.md | NOT found in b1.md | no evidence text | source not found: ..."}]
```

### refs.json — 参考文献表

```json
[{"key": "1", "entry": "甲方法. 规则框架. 2020.", "ts": "..."}]
```

`key` 与正文 `[n]` 引用对应；`export` 时随稿输出「参考文献」节，并做交叉核对。

## 交付产物（$AWC_OUT）

### result.json — 结构化结果（含 output_contract 全字段）

```json
{"case_id": "...", "skill": "academic-writing-client", "status": "complete|partial",
 "summary": "...", "main_output": ".../manuscript.docx", "artifacts": [{"path","kind","bytes"}],
 "sources": {"claims": [...], "refs": [...]},
 "changes": [...], "versions": [{"chapter","current_version"}],
 "export_report": {...}, "confirmations_needed": ["C2"],
 "uncertainty": "...", "limits": [...], "generated_at": "..."}
```

- `status=partial` 的触发源（可叠加）：材料 gaps、导出通道 failed、未核验论断、悬缺引用、未处置修订。
- 平台 `output_contract` 中的字段全部补齐（缺失置 null 并记入 uncertainty）。

### export_report.json — 导出审计

```json
{"md": {"status": "ok", "path": "..."}, "tex": {...}, "docx": {...},
 "pdf": {"status": "ok|failed", "tries": [{"tool","status","reason"}]},
 "readback": {"docx": {"status","paragraphs","headings","expected_headings"},
              "tex": {"status"}, "md": {"status","bytes"},
              "refs": {"status","citations","ref_keys","unresolved","unreferenced"}}}
```

### manuscript.md / .tex / .docx / .pdf

- `manuscript.md`：可编辑源（章节拼接 + 参考文献节）。
- `manuscript.tex`：`ctexart` 文档，标题/列表/公式已转换，编号与交叉引用交编译器。
- `manuscript.docx`：标准 OOXML（`[Content_Types].xml`、`_rels/`、`word/document.xml`、`word/styles.xml`），样式含 Title/Heading1-3/List Paragraph，Word/WPS/LibreOffice 可继续编辑。
- `manuscript.pdf`：latex 工具链渲染的预览；工具链缺失时本文件不存在，export_report 记 failed。

### session_state.json

`result` 收尾时对 project.json 的完整快照，便于第三方不读会话目录即可复核会话终态。
