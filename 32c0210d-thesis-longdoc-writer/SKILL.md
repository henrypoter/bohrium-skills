---
name: thesis-longdoc-writer
description: 学位论文与长文档写作（成稿优先）：逐章写满即时落盘 → 组装 manuscript.md+预览 → 最后跑 5 条核心一致性提示（只报告、不阻断、不返工）。纯标准库。
---

# thesis-longdoc-writer：成稿优先的长文档写作

**铁律：成稿充实度 > 机制完备度。** 顺序固定「定提纲 → 逐章写满 → 组装导出 → 最后才检查」。检查只写 uncertainty，**永不阻断导出、永不要求重写已完成章节**：宁可交有 3 处编号小瑕疵的完整论文，也不交半成品。

## 0 篇幅纪律（防草稿化）
- 总字数 ≥ 题面要求（未明示默认 30000、下限 8000）；每章 ≥ `min_words`（max(600,预算×60%)，参考/附录减半）。
- 硬禁 `【占位】`/`【待补充】`/`TODO`/「本章略」/只列要点/整章一段/提纲当正文。
- 每章写完**整章覆盖写入** `chapters/NN_*.md` 再写下一章；不追加碎片、不一次生成整篇。
- 预算 64 请求/900 秒，每案例 ≤12 请求（写作 ≤8）；先落诚实 result.json，告急立即 finalize。

## 1 主路径（4 步 5 命令）
输入 `/input/`（case/task/材料），先 `ls -la /input` 读实际文件、不按标签猜内容；脚本在 Skill 根 `scripts/`（装后 `/skills/weekly-skill/scripts/`）。产物在 `/app/work`（plan.json、chapters/）与 `/app/output`（manuscript.md+预览、consistency.json、changes.jsonl、result.json）。

**P0 盘点(0)** `mkdir -p /app/work /app/output; ls -la /input`；`python3 scripts/thesis.py --init --case /input/case.json`。

**P1 定提纲(≤1 请求)** `python3 scripts/thesis.py --plan --task /input/task.md --materials /input --workdir /app/work` → plan.json（每章 word_budget/min_words/材料映射/缺口）+全章骨架。有提纲照抄、不改结构；无提纲用下表默认学位论文章节；输入已是分章稿则原样复制，只补缺章。

**P2 逐章写满(每章 1 请求 ≤8)** 每章注入本章大纲＋对应材料片段(≤1500 字/文件)＋已完成章结论摘要(80 字/章)，按表写满后**立即落盘**：成段论述、小节用 `##`、图用题注行 `图N-M 标题`。数字/引用/图表只来自材料，拿不准写 `[待人工确认:原因]`；正文直接写 `图N-M/表N-M`，同章连续、先引后出；引用沿用 `[n]`/`[@key]`；缩写首现「中文全称（ABBR）」；缺材料写 `【缺口：原因】` 进 gaps，但该章仍写出可写部分。

| 章 | 篇幅(字) | 必含要素 |
|---|---|---|
| 摘要 | 300–500 | 问题/方法/数据/结果(数值)/结论 |
| 绪论 | 1200–2000 | 背景/现状/研究问题(≤3)/目标与贡献/结构 |
| 文献综述 | 1500–2500 | 主题分组(3–4)/方法对比/述评/研究空白 |
| 研究方法 | 1500–2500 | 数据来源/总体框架(配图)/步骤参数/指标/可复现 |
| 结果与分析 | 1500–2500 | 逐条答研究问题/图表+数值/基线对比/异常 |
| 讨论 | 800–1500 | 解释/文献对话/实践含义/局限(≥3)/效度 |
| 结论与展望 | 500–900 | 逐条答问题(数值)/贡献/未来工作 |
| 参考文献/附录 | — | 只收被引条目/补充材料 |

**P3 组装＋预览(0)** `python3 scripts/thesis.py --assemble --render --workdir /app/work --title "题目"` → 始终产出 manuscript.md，打印 `ASSEMBLE OK`(字数/达标) 与 `LENGTH`(各章/短章)；pandoc 出 HTML/docx/PDF，缺则记 uncertainty。哪章短只补哪章再重跑。

**P4 最后才检查(0)** `python3 scripts/consistency.py /app/work/chapters --out /app/output/consistency.json`，再 `python3 scripts/thesis.py --finalize --consistency /app/output/consistency.json`。结果只并入 uncertainty；**命中也照常交付，不重跑 P2、不改已完成章节**；仅一行能改的顺手改并 `--changelog`。打印 FINALIZE 即结束。

## 2 一致性：5 条核心规则
| 规则 | 级 | 判据 |
|---|---|---|
| cite-missing | issue | 引用无文献条目，或有引用无文献章 |
| float-missing | issue | 引用了 图N-M/表N-M 但无题注 |
| float-number | warn | 同章题注重号或断号 |
| term-abbr | warn | 缩写未给全称/先用后定义/多全称 |
| number-unsourced | warn | 摘要或结论数字未见于结果章 |

检查器 exit 恒 0：**只报告、不阻断导出、不要求重写已完成章节**，结果只进 `result.json.uncertainty`。

## 3 result.json 契约
`case_id`+`status`(success/partial/undeterminable/refused)+`status_reason`+`deliverables`+`source_map`({claim,source:"文件:行"}，覆盖数字/术语/引用/图表/论断)+`gaps`+`review_items`+`sources`+`uncertainty`+**output_contract 全字段**。无占位/缺口=success；有缺口/未确认=partial；材料不足=undeterminable；无法执行=refused。

## 4 异常处理
| 情况 | 处置 |
|---|---|
| 材料缺失/冲突 | 骨架+`【缺口】`进 gaps 不编造；冲突以 task.md/结果章为准记 changes；其余进 review_items |
| 引用无条目/断号/术语不一 | 记 uncertainty，不改写已完成章节 |
| 无 pandoc/字体/超长/告急 | 跳过渲染记 uncertainty；分章分节写；立即 finalize |
| 输入 PDF/docx | pdftotext/soffice 转文本，失败记 uncertainty |

## 5 示例（自拟，非正式结果）
`task.md`「3000字小论文，提纲：1.绪论 2.方法 3.结果 4.结论 5.参考文献」；`notes.md`「50 样本准确率 88.5%；CNN 基线；文献[1]提出注意力机制」。`PLAN OK`(每章 600 字下限) → 逐章写满落盘（结果章写「如表3-1所示」+题注）→ `ASSEMBLE OK`/`LENGTH` → cite-missing 进 uncertainty 照常交付 → `FINALIZE`。

## 6 依赖与自查
纯标准库；pandoc/soffice/xelatex 增强，缺则降级。限制：规则只覆盖机器可判项，语义一致性靠模型；缩写/数字/材料映射为启发式（映射需 P1 复核）；提纲≤12 章、每文件前 1500 字。schema/失败模式/对照见 `docs/`、`bench/`。自查：无占位、每章≥min_words、有预览、`python3 scripts/selftest.py` 与 `python3 bench/bench_run.py` 均 PASS。

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

## 补强：异常处置与可复现（阶段重做，2026-11-25）
| 异常 | 动作 |
|-|-|
| 文档格式不支持（.wps/.pages/加密） | 标 `skipped` + 说明支持的格式（.tex/.md/.docx），不假装转换，给可替代路径 |

可复现：`result.json` 增加 `doc_version`（稿件版本 + 原文件哈希）；每章给 `source_loc` 回指与字数/编号校验，长文档分章可独立复核。
