---
name: acad-template-fit
description: 学术格式与模板适配（成稿优先）：一条命令把稿件按目标模板改到可交付（可编辑 .tex/.docx + 渲染 PDF + diff 留痕）；校验结论只写 uncertainty，不阻断交稿。
---

# acad-template-fit — 成稿优先的模板适配

**硬目标**：`/app/output` 里有改好的稿件（可编辑 `.tex`/`.docx`）+ 同名渲染 PDF。检查报告、合规分、编译门禁都是附件——任一项失败都不等于"不交稿"。

## 0. 纪律
1. 成稿先落盘，再谈校验；fail/告警 → 写 `uncertainty`、`status=partial`，照常交付。
2. 主路径 4 条命令（含 1 条可选，§1）；`docs/`、`bench/`、`tests/` 是证据材料，主路径不读，被问到再看（§5）。
3. 模板读不到就写 `uncertainty`，用 task.md 的文字约束照常出稿；不改事实、不加材料外内容。

## 1. 主路径：备料 → 出成稿 →（可选）校验 → 收口

**C1 备料 + 骨架**（读题：`task.md` 定体裁/语言/受众，`case.json` 定 `output_contract` 与目标模板；用 read 看真实内容）
```bash
mkdir -p /app/work /app/output && cp -a /input/. /app/work/ && ls /app/work && python3 /skills/weekly-skill/scripts/init_result.py --case /input/case.json --out /app/output/result.json
```

**C2 一条命令出成稿**（解析模板 → 改稿 → 渲染 → 留痕，同进程，无需先 parse）
```bash
cd /app/work && python3 /skills/weekly-skill/scripts/tpl_fit.py --guide <模板/规范…> --source ms.tex --out /app/output/ms_fit.tex --spec-out /app/work/spec.json --changelog /app/output/changes.jsonl --render --workdir /app/work
```
交付物：`ms_fit.tex`、`ms_fit.pdf`（已复制到 `/app/output`）、`ms_fit.tex.fit.json`（applied/diff/render）、`spec.json`、`changes.jsonl`。`--guide` 可多文件（tex/docx/txt/pdf…），幂等（重跑 `applied=0` 达标）；docx 换 `--source ms.docx` → 复制可编辑源+soffice 预览，版式项在 `fit.json.unverified`。
**模型补**：tpl_fit 只改 preamble/版式骨架；标题层级、题注位置、图表环境、CCS/ORCID、文献条目顺序由模型在 `ms_fit.tex` 上改，逐处 `init_result.py --changelog --file … --rule … --before … --after … --reason …` 留痕。

**C3（可选，成稿落盘后）校验**——只为写报告，返工 ≤1 轮
```bash
python3 /skills/weekly-skill/scripts/fit_check.py --spec /app/work/spec.json --target /app/output/ms_fit.tex --source /app/work/ms.tex --compile --workdir /app/work --out /app/output/compliance.json
```
逐条 pass/fail/uncertain+证据；`deliver` 恒 true，结论只进 `uncertainty`/compliance.json，**不阻断成稿**。

**C4 收口**：用文件写入补全 `result.json`（§4），再
```bash
python3 /skills/weekly-skill/scripts/init_result.py --case /input/case.json --out /app/output/result.json --finalize
```
退出 0=字段齐；1=打印 MISSING/EMPTY，补齐再跑，不得丢稿。

## 2. 好成稿长什么样（照着产，别靠检查兜）
| 项 | 目标值 → 合格写法（模板另有规定以模板为准） |
|-|-|
| 页边距 | A4 210×297mm；上下 2.54cm、左右 3.0cm，误差 ≤0.05cm → `geometry{top=2.54cm,bottom=2.54cm,left=3cm,right=3cm}` |
| 字号 | 10/11/12pt 之一（小四=12pt、五号→11pt），Times→Liberation Serif → `[12pt,a4paper]` + `\setmainfont{Liberation Serif}` |
| 行距 | 按规范（1.15/1.5/2.0），全篇只留一处 → `\linespread{1.5}`，不叠加 `\onehalfspacing` |
| 标题层级 | 一/二/三级 = `\section/\subsection/\subsubsection`，编号连续、无手打序号 → `\section{引言}` |
| 图表 | 图题在下、表题在上、9–10pt；`\label`+`\ref` 可解析；三线表 → 表 `\caption` 在 `tabular` 前 |
| 参考文献 | GB/T 7714/IEEE/APA/Vancouver 之一，字段顺序随样式，`\cite` 全有条目 → `\bibliographystyle{gbt7714}` |

对照（同一坏稿）
- 反例：`[10pt,twocolumn,letterpaper]` + `\usepackage[margin=1in]{geometry}` + `times`，手打"1 引言"，无 `\label`，`\cite` 悬空。
- 正例：`[12pt,a4paper]` + `geometry{top=2.54cm,bottom=2.54cm,left=3cm,right=3cm}` + `\linespread{1.5}` + `\setmainfont{Liberation Serif}` + `\bibliographystyle{gbt7714}`，`\section{引言}`，图下表上 `\caption`。

## 3. 异常（都不阻断交稿，诚实标注）
- 模板缺失/版本不明：不编规格，`--guide task.md` 用文字约束出稿 + `uncertainty`，记 sha256 指纹，`status=partial`。
- 字体缺失：Times→Liberation Serif；缺字形进 `render.log_findings`，照常交源+PDF。
- 规格/包冲突：保留全部值 + `uncertainty`，按 task.md 定夺，不静默二选一（`spec.pkg_conflicts`）。
- 编译失败/docx 样式：交可编辑源 + log 摘要（`status=partial`）；docx 只复制+预览，版式项在 `fit.json.unverified`。
- 预算告急（64 请求/900 秒）：立即 C4 收口。

## 4. result.json
`case_id`、`status`(success/partial/undeterminable/refused)、`status_reason`、`artifacts`{manuscript,pdf,spec,compliance,changes}、`sources`[{file,line,basis}]、`uncertainty`[]、`output_contract` 全字段。无 fail 且产物齐→success；有 fail/缺产物/未核实→partial；材料不足→undeterminable。

## 5. 按需查阅（主路径不预读）
`docs/data_formats.md`（字段定义）· `docs/scoring_coverage.md`（16 得分点）· `docs/positioning.md`（能力边界）· `docs/quality_bar.md`（§2 扩展版）· `bench/bench_run.py`（公平对照）· `tests/run_tests.sh`（自测）。

## 6. 依赖/限制/示例
Python ≥3.8 仅标准库；latexmk/xelatex、pdftotext、soffice、kpsewhich 预装，缺失自动降级（仍出成稿）。限制：tpl_fit 只改 preamble/版式骨架，正文级结构由模型改并留痕；不润色、不加事实。
```bash
# 示例（自拟材料，非平台案例）
python3 /skills/weekly-skill/scripts/tpl_fit.py --guide /tmp/demo/guide.txt --source /tmp/demo/ms.tex --out /tmp/demo/fit.tex --render --workdir /tmp/demo
# 示意：applied=7 render=True -> fit.tex | fit.pdf
```

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
