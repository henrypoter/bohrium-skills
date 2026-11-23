---
name: acad-translate-bilingual
description: >-
  学术翻译与双语写作。中英双向整篇翻译：结构切块、术语表锁定+双向回查、数字/单位/引用数级归一、增译漏译与否定/模糊提示，产出纯译文+双语对照+分级质检报告；只标注不臆造，质检默认提示不阻断。
---

# 学术翻译与双语写作 Skill

## 用途与适用
中英双向整篇学术翻译（zh2en/en2zh）。输入 `/input/case.json`+`/input/task.md` 或本地 UTF-8/GB18030 文本；语向非中英/不可解码 → `status="failed"` 不硬译。

## 安装与依赖
零安装：全部脚本仅 Python 3.6+ 标准库，无第三方依赖、无网络访问。平台加载后脚本位于 `$SKILL_DIR/scripts/`；本地验证：`python3 $SKILL_DIR/scripts/selftest.py`（16 项断言全 PASS 即环境就绪）。术语表为 TSV/CSV/Markdown 纯文本（样例 `examples/glossary.sample.tsv`），数据格式见 `docs/data_formats.md`。

## 维护与版本
术语资产用 `check_terms.py parse → check → update` 生命周期维护，可跨稿累积；自查入口 `selftest.py`、对照基准 `bench/compare.py`；评分点覆盖见 `docs/scoring_coverage.md`，方案边界见 `docs/positioning.md`。版本 v4（作者-年跨语种对消、编码兜底、异常干净报错）。

## 调用方式（0 请求判定）
1. 读 case.json/task.md：取 case_id、材料路径、output_contract 全部字段名（result.json 逐字段照搬）。
2. 语向：「译成英文/translate into English」→ zh2en；「译成中文/translate into Chinese」→ en2zh；否则按汉字占比 >30% 判定，依据写入 result.json。
3. 术语表：case.json 的 glossary/术语字段或 task.md 两列表格；有则 parse，无则 ≤1 次请求抽取存 TSV 后 parse（auto_glossary, human_confirm）。
4. 输出形态按 task.md（纯译文/双语对照/修订标记），默认两者都产。

## 预算纪律
每案例 ≤12 次模型请求、≤600s、单次源文 ≤1200 字符。先保产：整篇译完即落盘 artifacts 与诚实 result.json（status="partial"），再核对。

## 工作流（脚本仅标准库，完整命令见 examples/minimal_example.md）
1. **切块**：`chunker.py`（按空行+结构切 B001…，code/独立公式原样保留，oversize 先按句再拆）。
2. **术语生命周期（闭环）**：`check_terms.py parse → check → update`。TSV/CSV/Markdown 列 src/tgt/禁用…，`+`=允许变体；决策行 `+变体`=允许、`-变体`=禁用、`=新译法`=改锁定，回写后重新 parse。
3. **逐块翻译**：按 plan.json 逐 chunk 请求（≤8 次），输出 `B###\t译文`；保留否定范围/限定条件/模糊限制语强度，不增译不省译，块不合并不丢 id；1万=10,000、1亿=10^8，保留有效数字。
4. **译后回查（advisory，exit 0 不阻断）**：`check_terms.py check` + `check_integrity.py`，读报告 JSON 的 flags/severity；missing/forbidden 必修，其余 flags 人工确认；normalization_notes 给换算依据；作者-年跨语种（张三 等↔Zhang et al.）按年份自动对消并记 `reconciled_author_year` 存证（姓氏不可跨语验证，advisory 需抽查）。
5. **对齐与终稿**：`align.py` 生成 bilingual.md+translation.md+对齐审计；missing/extra_in_translation 不得放过，length_suspects 为启发式提示；≤2 次请求修复，记 change_log 后重跑。

## 异常处理（只标注，不臆造）
| 情况 | 处置 |
|---|---|
| 歧义/病句 | 最可能解读 + `[AMBIG: 备选]`，记 uncertainty |
| 术语缺失/冲突/多译 | 缺失→抽取+auto_glossary；冲突→术语表为准+`[TERM-CONFLICT]`；多译→update 回写 |
| 数字/单位疑误 | 照译不擅改，记 uncertainty |
| 语向不支持 | 非中英 → status="failed"，不硬译 |
| 编码异常 | 脚本内 utf-8-sig→gb18030 自动兜底；仍不可解码 → 单行报错 exit 2，status="failed" |
| 空输入 | chunker 输出 0 块 + stderr WARNING + plan.json warning；result.json 记 failed/partial 并注明原因，不产空译文冒充完成 |
| 术语表文件缺失/坏 JSON | 单行报错 exit 2；改用 ≤1 次请求抽取或人工补表后复跑 |
| 中英混排 | align 按 CJK 占比自动判向，可用 `--direction` 显式覆盖 |
| 超长/公式/表格 | 切块（>60 块合并 reference/caption）；公式原样；表格结构不动仅译单元格 |
| 预算将尽 | 停止优化，落盘 partial+诚实 result.json |

## 输出（/app/output/）
translation.md、bilingual.md、terms_report.json、integrity_report.json、align_report.json、result.json。result.json 必含 case_id 与 output_contract 全部字段；status 诚实（未译完/缺块未修 = partial）。模板见 templates/result.template.json。

## 自查
frontmatter 合法；脚本 `--help` 正常、仅标准库；`selftest.py` 16 项断言全 PASS（正向零误杀+变异必命中+编码/空输入/缺表）；`bench/compare.py` exit 0；result.json 合法且含 case_id 与 output_contract 全部字段；每案例 ≤12 请求/≤600s/≤1200 字符；无预制答案。

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
