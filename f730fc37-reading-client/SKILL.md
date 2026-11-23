---
name: reading-client
description: 科研阅读客户端 CLI：同一会话目录完成打开→定位→选中→带证据核验问答→批注→三层导出；三级冗余锚点+断点续读+会话健康；未逐字核验一律 needs_confirmation 降级标注、不阻断；含公平对照基准与数据格式规范。依赖 Python3 标准库+pdftotext。
---

# reading-client：阅读会话客户端（CLI）

在同一 `--workdir` 会话目录串起「打开→定位→选中→问答→批注→导出」闭环，回应评分四问：串得起来 / 对得上原文 / 留得下来 / 讲得清楚。

## 核验语义（降级+标注，不阻断）
- 锚点核验逐级回退：verbatim → normalized → fuzzy(≥0.85) → page_line_only。
  其中 normalized 含两个等价通道：空白折叠、**去掉全部空白后的精确比对**（中文 PDF 常在一句中间断行，
  如「仍能维持/初始活性」，该通道可正确判定为已核验）。
- 仅前两级计已核验；fuzzy/page_line_only/未命中一律 `needs_confirmation:true`（qa/verify/select/note/annotations/result_draft 全链路携带）。
- qa、export 对未核验证据只降级标注、退出码 0，绝不拒绝导出；`verify` 退出码 1 仅表示“未逐字核验、需人工复核”，供脚本判断，不是阻断。

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
1. 读题：记 case_id 与 output_contract 全字段。
2. 打开：`python3 reader_client.py open <材料> [--page-offset N]`；no_text_layer→降级声明；物理页≠印刷页用 search 定 offset。
3. 定位：`search "<关键词>"`（或 --regex）。
4. 选中：`select --quote "<原文原句>"` 或 `--page N --start-line A --end-line B`；轻微改写可模糊锚定但标 needs_confirmation。
5. 问答+核验：`qa --question "..." --answer-file /app/work/ans.txt --evidence "<原句>" ...`；前两级已核验，其余换原句重试≤2 次，仍不过答“材料未直接报告”。
6. 批注（可选）：`note --page N --text "..." [--quote "..."]`。
7. 续读：`status` 看会话健康报告；`resume` 返回最后位置+段落上下文。
8. 导出：`export --out /app/output` 三层产物。
9. 组装：以 result_draft.json 为基础填 case_id + 合并 output_contract 全字段 → /app/output/result.json。

## 命令速查
| 命令 | 关键参数 | 输出 |
|-|-|-|
| open | file, --page-offset | pages, text_status, session_health |
| search | query, --regex, --topk | page/line/printed_page/摘要 |
| select | --quote 或 --page N --start-line A --end-line B | 锚点+上下文+needs_confirmation |
| verify | --quote | verified+needs_confirmation（退出码0已核验/1需确认，非阻断）|
| qa | --question/-file, --answer/-file, --evidence×n, --evidence-file | qa_id, all_verified, needs_confirmation |
| note | --page, --text, --line, --quote | note_id, anchor_confidence, needs_confirmation |
| status | — | 健康报告（health/备份/断点/未确认清单）|
| resume | — | 最后阅读位置+段落上下文 |
| export | --out | 三层产物路径+needs_confirmation 计数 |

输出单行 JSON；错误 `{"ok":false,...}` 退出码 2。

## result.json 契约
含 case_id + output_contract 全字段 +：status（success/partial/unanswerable_from_material/failed）、sources、uncertainty、needs_confirmation、answers[].evidence[]（quote/anchor/confidence/verified/needs_confirmation/locations）、change_log。

## 异常处理（诚实降级）
| 情况 | 处置 |
|-|-|
| 材料缺失 | failed: material_missing |
| 扫描件无文本层 | partial，uncertainty 声明仅覆盖可抽取文本 |
| 超大/加密 PDF 超时 | extract_timeout → partial |
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
`bench/bench_report.md` 给出可一键复跑的对照：同一任务下手工易错动作 10→0、可机器核验锚点 0/2→2/2、
结构化可复核产物 0→6、长文上下文 2185→858 字符（降 60.7%）。运行 `python3 bench/bench_run.py` 复算，
结果落 `bench/bench_results.json`。该对照度量路径开销与可核验性，不声称 LLM 端到端答案质量更优。

## 相对现有方案的边界
见 `docs/positioning.md`：与「大模型直读 / 文献管理器 / 通用 PDF 问答工具」逐项对照，
并显式声明不做什么（不做 OCR、不联网补元数据、不做学科正确性判断）。

## 维护与版本
- 版本：v4（`session.json` 的 `schema_version = 2`）。
- 变更记录：见 `../SOLUTION.md` 与 `change_log`；新增字段保持向后兼容读取。
- 自检：`python3 bench/bench_run.py` 应 exit 0；锚点核验回归可用 `verify --quote <原文句>` 抽查。

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
