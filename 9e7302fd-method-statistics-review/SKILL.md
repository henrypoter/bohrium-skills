---
name: research-methods-statistical-review
description: 研究方法与统计审查：按设计、变量、统计、样本量、结果报告五面逐项留痕，原句与内容哈希双定位，p-CI/样本流机检，严重度与待复核分级，缺页扫描统计输出等异常可降级交付
---

# 研究方法与统计审查

把稿件变成可逐条回复、可独立重跑的审查单。判对标准不是意见数量，而是：**每条落回真实原句；“做错”与“未报告/无法判断”分开；五面和六类检查均有记录；同一稿件哈希可重跑。** 不代写审稿结论，不作投稿决定，不覆盖文献综述、全文翻译和语言润色。

## 输入、输出与依赖

- 输入：`/input/case.json`、`/input/task.md` 和实际 PDF/MD/TXT/图表/统计输出；不得根据 case 标签猜论文内容。
- 输出：尽早写 `/app/output/result.json`（先 partial，再增量完善），可另附 issues.csv/REVIEW.md；保留原始 `output_contract` 全部字段和 `case_id`。
- 运行目录 `/app/work`；工具仅为 Python 3 标准库 `scripts/review_tool.py`，版本 `3.0.0`。
- 所有机检输出均是审查记录，不是正式案例答案；失败退出码 1，调用/读取错误退出码 2。

## 工作流与判对闸

### 0. 输入预检与版本锁定

PDF 可用环境中声明的工具实际抽取，文本页之间写 `\f`。扫描件 OCR 失败、缺页等不可假装抽取成功。建立 `manifest.json`（只记录实际情况）：

```json
{"expected_pages":[1,2,3],"unreadable_pages":[],"unresolved_figures":[],"missing_statistical_outputs":[],"missing_materials":[]}
python3 scripts/review_tool.py preflight --text /app/work/manuscript.txt --manifest /app/work/manifest.json
```

保存 `text_sha256` 到 `manuscript_version.sha256`，记录源文件名。预检失败不停止可读部分：将受影响检查面置 `pending`，状态置 `partial`，在 `unchecked` 说明范围。语言混杂仅是警告，不是缺陷。

### 1. 五面 + 六类双覆盖，不以“零问题”冒充“已检查”

| 五个方法学 facet | 必查锚点 |
|-|-|
| `design` | 研究问题与设计、对照、分组、随机化、盲法、偏倚控制、主要终点/假设是否事先明确 |
| `variables` | 暴露/结局/协变量/分组变量定义、测量、编码、切点、单位、缺失值、变量类型与模型匹配 |
| `statistics` | 数据结构与分布、独立性、重复测量、多重比较、交互项、敏感性分析 |
| `sample_size` | 效应量来源、alpha、把握度、估算依据；计划/入组/分析/失访/剔除数量衔接 |
| `reporting` | 效应量、CI、精确 p、统计量与自由度、摘要/正文/图表一致性、相应报告规范 |

六类 `categories` 固定为 `fact/citation/design/statistics/argument/compliance`。每个 facet 和 category 都写 `{status,notes,reason}`；status 为 `checked/not_applicable/pending/unchecked`。`checked` 写实际检查内容；其他状态写原因。**不建议只挑一个 facet 静默跳题；材料确实不涉及时用 `not_applicable`。**

```bash
python3 scripts/review_tool.py coverage /app/output/result.json
python3 scripts/review_tool.py coverage /app/output/result.json --allow-partial  # 仅用于诚实部分交付
```

### 2. 原句 + 细粒度定位 + 内容哈希

每条 issue 必须有：
- `location`：`section` 加 `page/paragraph/table/figure/item` 至少一个；定位从 1 开始；
- `quote`：单一连续原文，不改写、不拼接；`quote_sha256` 是 quote 经 NFKC、连续空白折为一个空格、去首尾空白后的 SHA-256；
- `evidence`：至少一条 `source_id + quote + locator + basis`，同样带哈希；`sources` 注册该来源全文内容 SHA-256；
- `claim/fix/severity/defect_type/review_status`。

```bash
python3 scripts/review_tool.py verify /app/work/issues.json --text /app/work/manuscript.txt
```

`quote_not_in_source` 必须修正或删除；`duplicates` 合并；哈希不匹配不能交付。原文不存在不能改写成“差不多”的话。无法定位的条目只能 pending，不得标 confirmed。

### 3. 可复算统计检查

从稿件或统计输出提取结构化记录到 `stats.json`，没有依据的数不填：

```json
{"statistics":[
 {"id":"S1","p":0.01,"ci_low":0.2,"ci_high":1.8,"scale":"linear","null":0},
 {"id":"S2","p":0.0455002639,"z":2.0,"df":20},
 {"id":"S3","n_enrolled":50,"n_excluded":5,"n_analyzed":45}
]}
python3 scripts/review_tool.py statcheck /app/work/stats.json
```

机检双侧 p-CI 方向（比值尺度默认 null=1）、双侧 z-p 复算、正整数自由度和 `enrolled-excluded=analyzed`。特殊区间、单尾检验、非标准重抽样不得硬套：标 pending 并人工复核。仅有额外未交代剔除时设 `accounting_incomplete:true` 并另列证据缺口。机检冲突必回原句/原表确认，不能把提取错误当论文错误。

### 4. 缺陷类型与严重度锚点

| `defect_type` | 含义 | 允许写法 |
|-|-|-|
| `fact_error` | 原文/数据/计算存在可证实冲突 | 引两处证据，按结论影响定级 |
| `evidence_gap` | 未报告、材料不足或证据不够 | 写“未报告/无法核实”，不得写成“作者做错” |
| `norm_issue` | 可指明规范条目的报告/合规问题 | 给规范名称与条目/版本 |
| `suggestion` | 可选改进 | 只能 `minor` |

`critical`：已证实的问题使主要结论不成立或数据不可信；`major`：影响可信度但可补救；`minor`：表达/格式或可选建议。缺效应量通常 major，不因“重要”一律 critical。`review_status` 只能 `confirmed/pending`；pending 必须进入 `uncertainty`。

### 5. 异常处置（先保存 partial，再恢复）

| 题面异常 | 识别与动作 | 最终状态/禁止事项 |
|-|-|-|
| 稿件缺页 | manifest 写 expected_pages；preflight 报 missing_pages | 缺页相关 facet pending；partial；不得推断缺失页内容 |
| 扫描件识别失败 | unreadable_pages、空文本或 decode_error_ratio>0.02 | 可重试环境允许的 OCR；仍失败列 unchecked；不得据乱码判缺陷 |
| 图表无法解析 | unresolved_figures 列图号 | reporting 相关项 pending；只审可读正文；不得声称图文一致 |
| 统计输出缺失 | missing_statistical_outputs 列文件/表号 | 原稿可审部分继续；复算项 pending；不得把“输出未提供”写成“方法错误” |
| 语言混杂 | preflight `mixed_language` 仅警告 | 保留原语言 quote，按原术语复核单位/否定词；不翻译后冒充原句 |
| 材料不足以判断 | missing_materials + facet/category pending + uncertainty | `partial`；列出所需最小材料；不给伪造确定结论 |
| 原文取不到/读取失败 | 记录实际 error 和已尝试路径 | 全文不可得则 failed；部分可读则 partial；不得称已审全文 |

### 6. 严格交付总闸

```bash
python3 scripts/review_tool.py schema /app/output/result.json   # 基础兼容检查
python3 scripts/review_tool.py gate /app/output/result.json     # 必须通过的最终检查
```

`gate` 校验版本内容哈希、run/tool 版本、原始 output_contract 保留清单、五面六类、定位与每条 quote/evidence 哈希、缺陷类型、严重度、pending 不确定性和 pass/issues/partial/failed 状态一致性。正式案例的 `gain` 由平台比较产生；没有真实同输入对照就填 null，**不编 benchmark 分数**。

## result.json 最小结构（字段示意，不是预置答案）

```json
{
 "schema_version":"3.0","case_id":"实际case_id","status":"issues",
 "manuscript_version":{"label":"实际版本","sha256":"64位文本sha256","files":["实际文件"]},
 "run":{"tool_version":"3.0.0","run_id":"本次实际运行标识"},
 "contract":{"source":"/input/case.json#/output_contract","preserved_fields":["实际原字段"]},
 "facets":{"design":{"status":"checked","notes":"…"},"variables":{},"statistics":{},"sample_size":{},"reporting":{}},
 "categories":{"fact":{},"citation":{},"design":{},"statistics":{},"argument":{},"compliance":{}},
 "issues":[{"id":"P1","category":"statistics","facet":"reporting","severity":"major","defect_type":"evidence_gap","review_status":"confirmed","location":{"section":"结果","page":2,"paragraph":3,"quote_sha256":"…"},"quote":"逐字原句","claim":"未报告效应量与CI","fix":"补报效应量和95%CI","evidence":[{"source_id":"M","quote":"逐字原句","basis":"该结果句仅见p值","locator":{"section":"结果","page":2,"paragraph":3,"quote_sha256":"…"}}]}],
 "sources":[{"source_id":"M","path":"manuscript.txt","sha256":"64位内容sha256"}],
 "checked_scope":{"did":[],"not_checked":[]},"gain":{"baseline_hit_rate":null,"skill_hit_rate":null,"false_positive_rate":null},
 "unchecked":[],"sources_note":"原始在线信息须另给URL和访问日期","uncertainty":[],"change_log":[]
}
```

`sources_note` 可省略；`/input/case.json` 要求的其他字段原样保留。最小可跑输入输出见 `bench/fixtures/`（合成示例，非正式测试）。

## 不适用与底线

不把未报告当做错，不把建议升格 major，不因模型常识直接判统计错误，不把自动规则输出当最终科学裁决。所有事实、来源和状态必须来自本次实际材料；不可复核的内容进入 pending/unchecked，绝不补造。

## 自测

```bash
python3 bench/bench_run.py
```

覆盖每个命令的正向零误杀和破坏性变异必命中，详见 `REVISION.md`。
