---
name: academic-writing-client
description: 命令行会话式学术写作客户端。章节级草稿+版本谱系；锚点定位最小化修订、逐条接受/拒绝留痕；论断-证据脚本化逐字回查核验；导出 Markdown/LaTeX/DOCX 双通道+PDF 预览+回读自检；会话状态机、断点续作、诚实降级。适用于"给定稿件与修改指令，交付带修订记录的可编辑文档"。
---

# 学术写作客户端（academic-writing-client）

核心脚本：`scripts/awc.py`（仅 Python 标准库）。状态存 `$AWC_ROOT`（默认 `/app/work/awc`），交付物写 `$AWC_OUT`（默认 `/app/output`），材料读 `$AWC_INPUT`（默认 `/input`）。

## 适用场景与触发

任务给出科研稿件/事实底稿 + 修改/写作/格式指令，要求修改落在指定位置、每处改动可追溯可逐条接受/拒绝、事实与引用有来源、导出可编辑文档（docx/LaTeX）时使用。3 个固定案例一律实跑，不预制答案。

## 预算纪律（硬约束）

- 每案例 **≤12 次模型请求**、全程 **≤600 秒**；单次 ≤16384 tokens，长材料分章处理，不整篇回读。
- **先交付后改进**：init+导入章节后先跑一次 `export`+`result` 写诚实 result.json（可 partial），再增量修订重跑；中断仍有可复核交付。
- 只用 Python 标准库与环境预装工具（`command -v` 探测）。

## 输入约定

- `/input/case.json`：取 `case_id` 与 `output_contract` 字段（result 自动补齐）。
- `/input/task.md`：任务说明与逐条修改指令；逐条落实为 revision。
- 材料文件：**读实际文件内容**，不按文件名/标签臆造。有 `/input/organizer-edit-workorder.json` 则按其章节清单导入。

## 工作流

```bash
S=<skill目录>/scripts/awc.py
python3 $S init --case-id <id> --title "<标题>"
python3 $S ingest --workorder /input/organizer-edit-workorder.json   # 或 --dir /input/chapters
python3 $S add-chapter ch1 --title "引言" --file /input/xxx.md       # 缺章记入 gaps
python3 $S revise ch1 --anchor '<原文>' --new '<改后>' \
    --reason '<依据：指令编号/事实底稿位置>' --source '<来源定位>' [--type revise|polish|format]
python3 $S claim --text '<论断/数字>' --evidence '<材料原文证据>' --source '<材料文件>' --locator '<章节>'
python3 $S verify              # 脚本化核验：证据必须能在来源文件逐字回查到
python3 $S refs add --key 1 --entry '<文献条目>'   # 建文献表；export 时随稿输出并交叉核对
python3 $S accept 1 ; python3 $S reject 2   # 逐条处置；reject 自动回退原文
python3 $S status              # 阶段/版本/未决修订/待确认论断/缺口
python3 $S export              # md/.tex/.docx + PDF 预览 + 回读自检
python3 $S result --case-id <id> [--summary '...'] [--uncertainty '...']
```

polish/format 修改同样走 `revise --type`，统一留痕。

## 核心机制

- **论断-证据脚本化核验**：`claim` 创建与 `result` 收尾时自动核验——证据必须在 `--source` 所指文件（相对 `$AWC_INPUT`/`$AWC_ROOT`/工作目录解析）逐字回查到；查不到或来源无法定位置 `needs-human` 并写 `verify` 原因，进入 `confirmations_needed`。
- **导出双通道+回读自检**：产出 `manuscript.md`（可编辑源）与 `.tex`（编号/交叉引用交编译器）；`.docx` 由 stdlib OOXML 写入器直写。写完后**回读**：解包 docx 核对标题、段落数、标题层级数与 md 源一致；核对 tex 含 `\begin{document}`/`\end{document}` 且标题已注入；结果写入 `export_report.readback`，不一致标 `mismatch` 降级。
- **引用-文献表交叉核对**：`refs add` 建文献表（key=正文 `[n]` 编号）；`export` 时把「参考文献」节写入 md/tex/docx，并核对正文 `[n]/[n,m]/[n-m]` 与文献表——悬缺引用标 `mismatch` 并使 result 降级 partial（公式内区间如 `$[0,1]$` 不误判）。
- **会话状态机**：`project.json` 记录 `phase`（init→ingested→revised→verified→exported→resulted）；原子写盘防崩溃损坏；`revise/export` 前校验章节存在，损坏状态明确报错。中断后 `status` 恢复。

## 输出契约（/app/output）

- `result.json`：`case_id`、`status`、`summary`、`main_output`、`artifacts`、`sources.claims`（含逐条 `verify`）、`changes`、`versions`、`export_report`（含 `readback`）、`confirmations_needed`、`uncertainty`、`limits`，及 `output_contract` 全部字段（缺项置 null）。
- `manuscript.md/.tex/.docx`：可编辑交付稿；`manuscript.pdf`：渲染预览（工具链缺失时诚实记 failed）。
- `session_state.json`、`export_report.json`：会话与导出审计。

## 异常处理（诚实降级）

| 情况 | 行为 |
|---|---|
| 材料缺失/章节文件不存在或为空 | 记 `gaps`（不入库空章节），其余照常，status=partial，limits 说明缺口 |
| 锚点定位失败/锚点为空/锚点==改后 | 退出码 3、不改稿；重读章节再修订，严禁整段覆盖与无改动伪修订 |
| 引用库缺失/正文引用悬缺 | `readback.refs` 标 mismatch（列出 unresolved），result 降级 partial 并写入 limits |
| 会话中断/损坏 | 状态在 `$AWC_ROOT`，原子写防损坏；损坏时明确报错 |
| 导出失败（无 latex/office 工具） | 保留 md/tex/docx，export_report 记 failed，result 降级 partial |
| 证据查不到/无来源 | `verify` 标 needs-human，列入 confirmations_needed，不新增材料外事实 |

## 最小调用示例

见 `examples/README.md`（自拟短材料完整命令序列与示意输出，标注为示例，非正式案例结果）。

## 限制

锚点为纯文本精确匹配（含公式行建议整行替换）；docx 为基础样式，复杂样式以 tex 为准；PDF 依赖环境预装 latex 工具链；引用核对覆盖数字编号引用，作者-年份制不做编号重排。

## 安装与维护

- **安装**：无。纯 Python 3 标准库，零 pip 依赖；`scripts/awc.py` 直接可执行。可选环境变量：`AWC_ROOT`（会话目录）、`AWC_OUT`（交付目录）、`AWC_INPUT`（材料目录）。
- **自测**：`python3 bench/bench_run.py` 一键复跑 18 项断言（正向零误杀/变异必命中/异常处置/双路径指标），exit 0 即通过；明细见 `bench/bench_results.json` 与 `bench/bench_report.md`。
- **数据格式**：会话与产物 schema 见 `docs/data_formats.md`；能力边界见 `docs/positioning.md`；评分点逐项核对见 `docs/scoring_coverage.md`。
- **维护**：状态文件全部为 UTF-8 JSON，损坏时按报错提示删除 `$AWC_ROOT/project.json` 重新 `init` 即可；历史版本在 `$AWC_ROOT/history/` 不受影响。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/write_tool.py claim_check result.json` 核验论断-引用回路，重点抓**数值论断无引用**与悬空引用；`structure` 查必需章节无缺无空。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：论断与引用绑定、章节缺项检测、三向一致。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/manuscript_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/manuscript_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
