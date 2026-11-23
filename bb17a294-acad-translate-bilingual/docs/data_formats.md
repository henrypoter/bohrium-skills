# 数据格式说明（全部 UTF-8 纯文本，第三方可直接复用）

## 1. blocks.jsonl（chunker 产物，源文切块）

每行一个 JSON 对象：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | `B001…`，按空行+结构顺序编号 |
| type | string | `heading/paragraph/caption/table/reference/code` |
| translate | bool | code/独立公式为 false，原样保留不进翻译请求 |
| text | string | 块原文（已 strip） |

## 2. plan.json（翻译请求计划）

`{"max_chars":1200, "n_blocks":N, "n_chunks":M, "chunks":[{"ids":["B001",…],"oversize":false}], "warning":null}`。`oversize=true` 的块须先按句再拆；`warning` 非空（如空输入）须在 result.json 中说明。

## 3. tgt_blocks.jsonl（模型译文回填）

每行 `{"id":"B001","text":"译文"}`；id 必须与 blocks.jsonl 一一对应，不合并不丢块。

## 4. 术语表（TSV/CSV/Markdown 三格式均可 parse）

列：`源术语 <TAB> 锁定译法 [<TAB> 禁用译法…] [<TAB> +允许变体…]`。首行表头（source/src/term/原文/源术语）自动跳过；`#` 注释行跳过。样例见 `examples/glossary.sample.tsv`。

## 5. decisions.tsv（术语维护决策，check_terms update 输入）

每行：`源术语 <TAB> +变体`（加入允许）/ `-变体`（加入禁用）/ `=新译法`（改锁定）。回写后重新 parse 形成生命周期闭环。

## 6. bilingual.md（双语对照产物）

按块分节：`### B001 [type]` + `**原文**` + `**译文**`，可直接进入作者修改流程；translation.md 为同序纯译文（translate=false 块原样回填）。

## 7. terms_report.json（check_terms check 产物）

`terms_total / ok / issues[]（term, expect, src_hits, tgt_hits, src_lines, tgt_lines, problems[]）/ pass / severity{critical,major,minor} / note`。problems 取值：`missing_in_translation`、`variant_risk: cover n/N`、`not_in_source`、`forbidden_variant:X xN`。

## 8. integrity_report.json（数字/单位/引用/语义）

- `numeric`：`src_items / tgt_items / missing_in_tgt / added_in_tgt / approx_pairs[]（hint: rounding/typo|scale slip, ratio）/ normalization_notes[]`（换算依据，如 `2.3亿=2.3e+08`，限 60 条）。
- `citations`：`src_items / tgt_items / missing_in_tgt / added_in_tgt / reconciled_author_year[]`（`ayc:2020<->ay:Zhang:2020 x1 …`，按年匹配，姓氏未验证，advisory）。
- `semantic`：`counts{negation,hedge,causal: src/tgt 各[中,英]} / flags[] / note=advisory`。
- 顶层：`tolerance_policy / severity{critical,major,advisory} / pass / note`。容差策略：年份/引用/带单位量/范围零容差；裸数字允许跨数级等价，近似值入 approx_pairs 提示。

## 9. align_report.json（对齐审计）

`blocks_src / blocks_tgt / direction / missing_in_translation[] / extra_in_translation[] / kept_verbatim[] / length_suspects[]（block, flag: possible_omission|possible_addition, ratio）/ severity / pass / note`。

## 10. result.json（案例契约，模板 templates/result.template.json）

必含：`case_id`、`status`（success/partial/failed，partial 必须注明原因）、`direction`、`artifacts`、`sources`、`glossary`（来源/auto_extracted/human_confirm）、`checks`、`change_log[]`（block/before/after/reason）、`uncertainty[]`、`budget`。case.json 声明的 output_contract 字段逐字段照搬置顶。

## 复用约定

- 全部脚本 `python3 script.py --help` 可查参数；仅标准库，Python 3.6+。
- 所有 QC 脚本 exit 0 advisory（读报告 flags）；输入不可读/不可解码 exit 2 并打印单行错误。
- 术语表、decisions、bilingual.md 均为纯文本，可用任意编辑器/git 维护。
