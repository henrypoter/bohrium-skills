---
name: evidence-bound-manuscript
description: 学术论文写作工作流。把给定科研材料（txt/csv/md/pdf/docx/图片）整理为带行号的材料索引与图表清单，生成事实论断绑定材料区间或文献条目的 IMRaD 章节稿（Markdown/docx + 渲染 PDF + 证据映射表），脚本核对数值单位、引文-行号区间定位、图表三向对齐、引用元数据、章节齐备与 overclaim 风险，输出诚实标注缺口的 result.json。适用于依据固定材料写论文初稿/章节稿；不适用于无材料自由创作。
---

# 证据绑定式学术论文写作

目标：写得实、引得对、全得起来、改得动。禁止凭记忆补全数值/文献；事实性内容必须逐条回溯到材料区间或文献条目，改动留痕，缺口显式标注。

## 资源

- `scripts/manuscript_tool.py`：三合一工具（仅标准库；调预装 pdftotext/pandoc，PDF 经 pandoc+xelatex/pdflatex；缺工具时用 latex-compiler/office-renderer 代替）。子命令 `extract`/`check`/`build`。
- `examples/EXAMPLE.md`：最小调用示例（自拟短材料，非正式案例）。

## 预算纪律

每案例 ≤12 次模型请求、全程 ≤600 秒。**先写诚实的 result.json 占位（case_id、status、已识别缺口），再增量改进**；失败不得回退为捏造内容；材料超长时按章节需要分段读。

## 标准流程（每案例）

1. **读题（1 次请求）**：读 `/input/case.json`（记录 `case_id`、`output_contract` 全部字段名）与 `/input/task.md`（体裁、章节、字数、引用格式约束）。立即写 `/app/output/result.json` 诚实占位：`case_id`、`status:"in_progress"`、`outputs:null`、`sources:[]`、`uncertainty`，output_contract 各字段置 null。
2. **抽取**：材料复制到 `/app/work` 后运行
   `python3 scripts/manuscript_tool.py extract --src <材料目录> --dst /app/work`
   得到带 `L0001` 行号文本 + `figure_inventory.json`（材料中图/表提及）。图片/二进制标 SKIP，由你直接读图并手工登记。据此写**材料索引**（材料 → 支撑哪一节 → 行号区间），记入 draft.json 的 `sources`。
3. **写 draft.json（核心产物，见下）**：按 IMRaD 或题面结构写作；数值、单位、样本量、显著性、图注、文献元数据逐字取自证据引文，禁止改写数字。
4. **一致性检查**：
   `python3 scripts/manuscript_tool.py check --draft /app/work/draft.json --report /app/output/check_report.json --materials /app/work`

   `--materials` 指向 extract 产物目录，启用引文-区间核对与图表三向核对。fail 必须修复或显式降级（缺口写入 `uncertainty`/`human_review`）；exit code 1 = 仍有 fail。
5. **渲染交付**：
   `python3 scripts/manuscript_tool.py build --draft /app/work/draft.json --outdir /app/output`
   产出 `manuscript.md/.docx`（可编辑）+ `manuscript.pdf`（渲染预览）+ `evidence_map.md`（段落→材料区间/文献映射表），并合并 `result.json`（自动并入 output_contract 字段名，缺项写入 uncertainty）。**output_contract 实质内容由你按题面填入**，不得留空冒充完成。
6. **收尾**：pdftotext 抽 PDF 文本复核（摘要与结果一致、图注编号连续、声明齐备）；`status` 更新为 `complete`/`partial`（写明限制），全部文件放入 `/app/output`。

## draft.json 结构

```json
{
 "meta": {"case_id": "…", "status": "partial|complete"}, "title": "…", "abstract": "…",
 "required_sections": ["Abstract","Introduction","Methods","Results","Discussion","References"],
 "sections": [{"heading": "Results", "paragraphs": [
   {"text": "…42.3%（对照 100%）…[@key1]", "kind": "fact", "strength": "hedged",
    "evidence": [{"material": "exp_notes.txt", "loc": "L0003-L0004", "quote": "材料原文逐字片段"},
                 {"citation": "key1"}]}]}],
 "figures": [{"id": "1", "caption": "…", "source": "exp_notes.txt L0005", "caption_missing_in_source": false}],
 "citations": {"key1": {"authors": "…", "year": "…", "journal": "…", "doi": "10.xxxx/…", "unverified": false}},
 "terms": {"缩写": "全称"},
 "sources": [], "uncertainty": [], "change_log": [], "human_review": [],
 "data_availability": "…（题面要求时填）"
}
```

规则：
- 段落 `kind` 缺省 `fact`（必须有 evidence）；评述/过渡段设 `"kind":"comment"`（无证据只 warn）。`strength` 填 `strong`/`hedged`；正文出现「证明/首次/导致/prove/demonstrate」等强论断词而证据无统计标记（p 值/显著/CI）时 check 提示 overclaim。
- `evidence.quote` 必须是材料**逐字**片段（可按行拆为多个片段），`loc` 必须是其行号区间。check 双通道核对：归一化匹配（空白折叠/连字符换行/µ-μ 统一）+ **片段必须落在所标区间内**（他处找到 = 位置错配 fail；找不到 = 疑似编造 fail）。
- 正文每个数值与「数值+单位」必须在该段证据引文中逐字出现（年份豁免）。正文引用写作 `[@key]`。
- figures 与正文双向核对：正文每个「图/表 N」必须在清单中（否则 fail），清单每个图表至少被引用一次（否则 warn）；图注数值与 source 行核对；材料中未登记的图表提及会 warn。

## 事实纪律与改动留痕

- 数字、单位、样本量 n、显著性、图注：只许照抄，不许换算/四舍五入/补全；确需换算时新旧值都保留并记入 `change_log`。
- 趋势不写成因果，除非材料明确支持。文献元数据必须与材料或可查记录一致；改稿的所有修改记入 `change_log`。

## 异常处理（禁止编造）

| 情况 | 处置 |
|-|-|
| 材料缺图注 | `caption` 留空 + `caption_missing_in_source:true`，成稿显示 `[CAPTION-MISSING]` 占位，列入 `human_review` |
| 图表与正文/材料冲突 | 不擅自裁决：正文按原始数据，冲突点写入 `uncertainty` + `human_review` |
| 文献取不到全文 | 条目保留并设 `"unverified": true`，只用材料已给元数据，写入 `uncertainty` |
| 材料超长 | 分段抽取阅读，索引覆盖全部文件；未读部分在 `uncertainty` 声明限制 |
| 引用格式不认识 | 保留原格式键，按作者-年/数字制就近映射，记入 `change_log` |
| 编译/工具缺失 | `pdf_status`/`docx_status` 如实记录原因，仍交付 md 可编辑稿 |

## 失败与部分结果

任何阶段失败：`status="partial"`，`outputs` 指向已生成的最好稿件，`uncertainty` 写明缺什么、为什么；绝不删除诚实中间结果。

## 自查（提交前）

1. `check` 无 fail（或已转化为显式标注的缺口）；2. `result.json` 含 output_contract 全部字段 + case_id + status/sources/uncertainty；3. `/app/output` 内 md/docx 可编辑 + pdf 预览 + evidence_map.md 齐全；4. 无待办标记残留，无材料外事实。

## 最小调用示例

见 `examples/EXAMPLE.md`（自拟短材料演示 extract→draft→check→build 全流程；非正式案例结果）。

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
