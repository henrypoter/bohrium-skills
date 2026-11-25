---
name: reading-client
description: 科研阅读客户端 CLI v5：同一会话完成打开→定位→选中→问答→批注→导出；除页/行+三段式锚点外，用材料哈希、answer_id/answer_sha256、selection_sha256 和 evidence_id 绑定答案，独立 audit 检原文/选区/答案/批注漂移。inspect 预检加密与超大文件，失败仍导出诚实 partial；含版本化 result.json、契约合并与变异 bench。依赖 Python3 标准库，PDF 另需 pdftotext。
---

# reading-client：阅读会话客户端（CLI）

在同一 `--workdir` 会话目录串起「打开→定位→选中→问答→批注→导出」闭环，回应评分四问：串得起来 / 对得上原文 / 留得下来 / 讲得清楚。

## 核验语义（降级+标注，不阻断）
- 锚点核验逐级回退：verbatim → normalized → fuzzy(≥0.85) → page_line_only。
  其中 normalized 含两个等价通道：空白折叠、**去掉全部空白后的精确比对**（中文 PDF 常在一句中间断行，
  如「仍能维持/初始活性」，该通道可正确判定为已核验）。
- 仅前两级计已核验；fuzzy/page_line_only/未命中一律 `needs_confirmation:true`（qa/verify/select/note/annotations/result_draft 全链路携带）。
- qa、export 对未核验证据只降级标注、退出码 0，绝不拒绝导出；`verify` 退出码 1 仅表示“未逐字核验、需人工复核”，供脚本判断，不是阻断。

## 答案—原文绑定（新增硬闸）
- `open` 记录材料 `{path,bytes,sha256,format}`；每个 QA 固定 `answer_id + answer_sha256 + document_sha256 + selection_sha256`，每条证据固定 `evidence_id + answer_id + document_sha256 + TextQuoteSelector + physical_page/line`。
- `scripts/delivery_guard.py audit` 用**独立实现**重读原文、逐页文本、session 与导出，不接受 fuzzy/page_line_only 冒充已核验。改答案、改选区、换原文、换引文、删材料版本或改 annotations.json 都会 exit 1 并写入 `binding_audit.json`。
- 哈希用于发现版本漂移，不是密码学签名；机械绑定证明“答案—选区—引文—材料版本一致”，**不证明答案语义上必然充分**。导出 status=success 之外还需 audit 通过方可视为机器绑定检查通过。

## 安装与依赖
- 无第三方 Python 依赖，仅用标准库；复制 `submission/` 目录即可用，无需 pip 安装。
- 可选外部工具：`pdftotext`（poppler-utils，处理 PDF 时必需；缺失时报 `tool_missing`）。
- 调用方式：`python3 reader_client.py --workdir <会话目录> <子命令> [参数]`；`--workdir` 必须写在子命令之前。

## 支持格式
| 格式 | 处理方式 | 说明 |
|-|-|-|
| `.pdf`（有文本层） | `pdftotext -layout`，不足 40 字符回退 raw | 按 `\f` 分页 |
| `.pdf`（扫描件/无文本层） | 文本层近空 → `text_status=no_text_layer` | 显式降级，不 OCR、不编造 |
| `.txt` / `.md` / 其它纯文本 | 直接读取，按 `\f` 或整篇为一页 | — |
| 图片（png/jpg 等无文本层） | 同扫描件降级路径 | 不猜测图内文字 |

## 预算纪律
- 每案例 ≤12 次请求、≤600 秒（平台总预算 64 请求/900 秒/响应 16384 tokens）。
- 先写诚实 result.json 再增量改进：第 4 步后立即 export 组装保底。
- 用 search/select 摘要输出，不整页读入上下文。

## 标准工作流
输入 /input/case.json、task.md 与材料；会话目录默认 /app/work/reader_session（多案例 `--workdir sess_<case_id>`）。
1. 读题：记 case_id 与 output_contract 全字段；材料预检：`python3 scripts/delivery_guard.py inspect <材料>`，加密/超限立即按表降级，不浪费时间抽取。
2. 打开：`python3 reader_client.py --workdir /app/work/reader_session open <材料> [--page-offset N] [--max-file-mib 64] [--max-pages 2000]`；open 内也会强制同样预检，并检查 pdftotext 返回码/stderr。
3. 定位：`search "<关键词>"`（或 --regex）。
4. 选中：`select --quote "<原文原句>"` 或 `--page N --start-line A --end-line B`；轻微改写可模糊锚定但标 needs_confirmation。
5. 问答+核验：`qa --question "..." --answer-file /app/work/ans.txt --evidence "<原句>" ...`；前两级已核验，其余换原句重试≤2 次，仍不过答“材料未直接报告”且保持 partial。
6. 批注（可选）：`note --page N --text "..." [--quote "..."]`。
7. 续读：`status` 看会话健康/材料版本/打开错误；`resume` 返回最后位置+段落上下文。
8. 导出并终稿：`export --out /app/output --case /input/case.json` 自动生成 reading_record.md、annotations.json、result_draft.json，并保留 output_contract 键生成 result.json；不传 --case 时只产 draft，须按原契约手工终稿。
9. 独立复核：`python3 scripts/delivery_guard.py audit --workdir /app/work/reader_session --result /app/output/result_draft.json`；失败须修复并重新 export+audit，不能仅改哈希绕过。

## 命令速查
| 命令 | 关键参数 | 输出 |
|-|-|-|
| `scripts/delivery_guard.py inspect` | file, --max-file-mib | material_version 或 encrypted_pdf/oversized_file，错误 exit 1 |
| open | file, --page-offset, --max-file-mib, --max-pages | pages, text_status, material_version, session_health |
| search | query, --regex, --topk | page/line/printed_page/摘要 |
| select | --quote 或 --page N --start-line A --end-line B | 锚点+上下文+needs_confirmation |
| verify | --quote | verified+needs_confirmation（退出码0已核验/1需确认，非阻断）|
| qa | --question/-file, --answer/-file, --evidence×n, --evidence-file | qa_id, all_verified, needs_confirmation |
| note | --page, --text, --line, --quote | note_id, anchor_confidence, needs_confirmation |
| status | — | 健康报告（health/备份/断点/未确认清单）|
| resume | — | 最后阅读位置+段落上下文 |
| export | --out, --case（可选） | 三层产物+版本/run_id；--case 另产最终 result.json |
| `scripts/delivery_guard.py audit` | --workdir, --result | 绑定报告；通过 exit 0，任何漂移/脱锚 exit 1 |

reader_client 输出单行 JSON，操作错误 `{"ok":false,"code":...}` 退出码 2；delivery_guard 输出结构化报告，预检/审计不通过退出码 1。export 遇到不可读材料仍退出 0 是为了保住诚实 partial 产物，不表示读取成功。

## result.json 契约
含 case_id + output_contract 全字段 + `schema_version/tool_version/run_id/material_version/open_error/artifact_manifest`，以及 status（success/partial/unanswerable_from_material/failed）、status_reason、sources（含抽取器/页数/页码偏移）、uncertainty、needs_confirmation、change_log。`answers[]` 带 answer_id/answer_sha256/document_sha256/selection/selection_sha256；`evidence[]` 带 evidence_id/answer_id/document_sha256/quote/location/anchor/confidence/verified/needs_confirmation/locations。annotations.json 同步材料版本与答案哈希，artifact_manifest 对其余产物做 SHA-256。

## 异常处理（诚实降级）
| 情况 | 处置 |
|-|-|
| 材料缺失 | failed: material_missing |
| 扫描件无文本层 | partial，uncertainty 声明仅覆盖可抽取文本 |
| 加密 PDF | inspect/open `encrypted_pdf`（文件字典或 pdftotext 密码错误）；请求无密码副本/合法解密，不绕过权限；export 保留 partial+open_error |
| 超大文件 | 默认 >64 MiB 为 oversized_file，>2000 页为 oversized_document；按章节分卷/请求文本或显式提高限额，不假装读全 |
| 抽取超时或 PDF 其他错误 | extract_timeout / pdf_extraction_failed → partial；记录 stderr 摘要与可接管动作 |
| 材料被替换、答案/选区/引文被编辑后脱锚 | audit exit 1；回到原版本重定位并重新 qa/export，不得只更新哈希 |
| 问题超出材料 | 答“材料未报告”，unanswerable_from_material |
| 锚点降级 | needs_confirmation + 导出 uncertainty 声明 |
| 会话损坏 | 自动回退 .bak（recovered_from_backup）；主备均坏 fresh_after_corruption 空会话 |
| 选区跨页 | 拆两条 select --quote 各自核验 |
| 批注/导出写入失败（权限、磁盘满） | 报 `write_failed: <路径>`，已生成的部分产物保留；改 `--out` 可写目录重试，`status` 说明缺哪件 |
| 接口/权限异常（工具缺失、超时、文件被占用） | `tool_missing` / `extract_timeout` / `file_locked` 明确报错并降级为 partial，绝不返回空结果冒充成功 |

## 数据格式与复用
会话态、逐页文本、锚点、批注、结果与阅读记录的全部字段定义见 `docs/data_formats.md`。
`annotations.json` 采用 W3C Web Annotation（`TextQuoteSelector`），可被支持该标准的标注工具消费；
`session.json` 带 `schema_version`，字段变更保持向后兼容。他人只需实现「逐页文本 + 三段式锚点」
两个最小结构，即可独立复算任一答案能否追溯到原文。

## 公平对照（增益的可验证证据）
`bench/bench_report.md` 与 `bench/bench_results.json` 保留上一版确定性路径对照记录（手工动作、锚点、上下文开销），它们是本地合成样例记录而非官方增益。当前 `python3 bench/bench_run.py` 运行 19 项正向/变异回归（含新 guard 12 项），不覆盖旧 JSON；复算输出即为退出码与逐项 PASS/FAIL。两类证据都不声称 LLM 端到端答案质量更优。

## 相对现有方案的边界
见 `docs/positioning.md`：与「大模型直读 / 文献管理器 / 通用 PDF 问答工具」逐项对照，
并显式声明不做什么（不做 OCR、不联网补元数据、不做学科正确性判断）。

## 维护与版本
- 版本：v5.0.0（`session.json`/`result.json` 的 `schema_version = 3`；独立 guard 1.0.0）。
- 变更记录：见 `REVISION.md` 与 `change_log`；对旧 session 缺字段的情况 audit 会明确报未绑定，不静默升级成已核验。
- 自检：`python3 bench/bench_run.py` 应 exit 0（19 项）；新增能力单独跑 `python3 bench/bench_delivery_guard.py`（12 项）。

## 限制
- 核验基于文本层；公式/图内文字/表格结构不在范围（注明）。
- 页码=PDF 物理页；印刷页经 --page-offset 换算。
- 不渲染页面；扫描件不做 OCR（降级处理）。
- 离线无元数据，不生成 BibTeX（避免编造）。

## 最小调用示例
见 EXAMPLE.md（自拟材料，输出均为示例）。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/read_tool.py support_check answers.json --text source.txt` 把每条证据引文在原文里做逐字匹配，不在原文的（误报）直接揪出；支持度分档统计。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：证据逐字回链、支持度分档。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/support_rubric.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/support_rubric.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
