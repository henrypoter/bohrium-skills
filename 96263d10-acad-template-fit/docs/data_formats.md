# 数据格式规范（可复用）

本 Skill 的中间态与产物均为纯 JSON / JSONL / unified diff 文本，**无私有二进制格式**，可被其它工具直接读取、复算与复用。五个脚本均为独立 CLI（仅 Python 标准库）。

## 1. `spec.json`（tpl_parse.py 产出：模板检查项清单 + 指纹）

| 字段 | 类型 | 说明 |
|-|-|-|
| `files` | array | 参与解析的输入文件 |
| `items[]` | obj | 检查项：`{id, key, requirement, value, unit, source_file, source_line}`；key 如 `page.size`/`page.margin_top`/`page.columns`/`body.font_size`/`body.line_spacing`/`refs.style`/`caption.figure.position`/`caption.table.position`/`table.three_line`/`page.count`；中文字号 value 保留原名（如"小四"），unit 记 `=12pt` |
| `conflicts[]` | obj | `{key, values[], note}`；归一化比对后仍不同的值**全部保留**并显式 flag，不静默二选一 |
| `warnings[]` | str | 解析级告警（如 Times 字体建议换 Liberation Serif、docx XML 不可读） |
| `fingerprints[]` | obj | `{file, sha256}`：模板版本指纹，复核时校验"同一份模板" |
| `versions[]` | obj | `{file, type(class/package), name, version}`：`\ProvidesClass/Package` 抽取；缺失即"版本不明" |
| `packages[]` | str | `\usepackage/\RequirePackage` 清单（去重排序） |
| `pkg_conflicts[]` | obj | `{packages[], note}`：已知冲突对（natbib+biblatex、inputenc+fontspec、float+floatrow、hyperref 重复） |

## 2. `<out>.fit.json`（tpl_fit.py 产出：确定性改稿记录）

`tpl_fit.py` 的两种入口等价：`--spec spec.json`（先 parse 后 fit，供脚本/回归使用）或 `--guide <模板或规范文件…>`（**一条命令**内联解析，主路径用这个；`--spec-out` 可同时落盘 spec.json）。

| 字段 | 说明 |
|-|-|
| `source`/`out`/`spec` | 输入输出定位（source 绝不被改写）；走 `--guide` 时 `spec` 记 `(in-process from --guide)` 或 `--spec-out` 路径 |
| `mode` | `tex-fit`（确定性改 preamble）或 `docx-passthrough`（复制可编辑源 + soffice 渲染预览，样式项交模型） |
| `applied` | 实际改动规则数；幂等：对已合规稿 applied=0（docx 模式恒 0） |
| `changes[]` | `{rule, before, after, spec_id, reason?}`，与 changes.jsonl 同构 |
| `diff` / `diff_plus` / `diff_minus` | unified diff 全文及 +/- 行数 |
| `render` | 可选（`--render`）：同 §3 `compile` 结构，另加 `pdf_delivered`——交付用 PDF 已复制到 `<out>` 同目录 |
| `warning` | guide 未抽到任何可核对项时的显式告警（稿件按原样复制，须写入 uncertainty） |
| `unverified[]` | 仅 docx 模式：`{key, expected, reason}`，列出需模型按 `docs/quality_bar.md` 改的样式项 |

## 3. `compliance.json`（fit_check.py 产出：分级核对 + 编译验证）

| 字段 | 说明 |
|-|-|
| `checks[]` | `{key, requirement, expected, status(pass/fail/uncertain), evidence, severity(info/error/warning)}`；evidence 含实测值与换算（如 `geometry top=1in vs spec 2.54cm (= 2.54cm vs 2.54cm)`） |
| `fidelity[]` | 内容单元计数不一致告警：`figures/tables/footnotes/citations/sections/equations` 六类，`source=N target=M -- investigate` |
| `conflict_precheck[]` | 模板 spec 包冲突 ∩ 目标稿实际加载包 |
| `compile` | `{attempted, compiler, ok, pages, log_findings[], pdf?}`；无编译器时 `attempted=false` 诚实降级；门禁 = PDF 存在且最终 .log 无致命 `! ` |
| `unverified_items[]` | 无自动规则、须人工核对的项（如 `table.three_line`），**不假装已核** |
| `summary` | `{pass, fail, uncertain}` 计数 |
| `readiness` | `{ready, level(ready/partial/undeterminable), deliver(恒 true), errors[], warnings[]}`：告警式判定，不阻断交付 |

## 4. `changes.jsonl`（tpl_fit.py / init_result.py 追加：修改留痕）

一行一条：`{"ts": "ISO-8601 UTC", "file": "...", "rule": "...", "before": "...", "after": "...", "reason": "..."}`。
`init_result.py --logsummary` 按 rule 聚合计数复核；tpl_fit 每条 change 自动落一行，模型手工改动用 `init_result.py --changelog` 补记。

## 5. `result.json`（init_result.py 骨架/校验：平台契约）

| 字段 | 说明 |
|-|-|
| `case_id` | 镜像 case.json |
| `status` | `success/partial/undeterminable/refused` + `status_reason` |
| `sources[]` | 事实与来源定位（file/line/basis） |
| `uncertainty[]` | 缺口与未确认项（诚实标注） |
| 其余 | 镜像 `output_contract` 全部字段；`--finalize` 缺字段/空值退出 1 |

## 6. 脚本接口速查

| 脚本 | 主路径用法 | 说明 |
|-|-|-|
| `tpl_fit.py` | `--guide <模板…> --source ms.tex --out out/ms.tex --spec-out work/spec.json --changelog out/changes.jsonl --render --workdir work` | **一条命令出成稿**：解析+改稿+渲染+留痕+PDF 落到 out 同目录 |
| `fit_check.py` | `--spec work/spec.json --target out/ms.tex --source ms.tex --compile --workdir work --out out/compliance.json` | 可选校验，结论只写报告不阻断 |
| `tpl_parse.py` | `<模板…> --out work/spec.json` | 单独抽检查项（`build_spec()` 亦供 tpl_fit 内联调用） |
| `init_result.py` | `--case case.json --out out/result.json` / `--finalize` / `--changelog` | 骨架、校验、留痕 |
| `bench_run.py` | 无参数 | 三路径对照（baseline / 全功能 skill / 主路径 lean） |

## 复用约定

- 消费方只需 `spec.json` 的 `items[]`（§1）与 `compliance.json` 的 `checks[]`（§3）即可复算任一规格项的判定依据。
- 新增 key 不影响旧消费方；`changes.jsonl` 只追加不覆写；`result.json` 覆盖需显式 `--force`。
