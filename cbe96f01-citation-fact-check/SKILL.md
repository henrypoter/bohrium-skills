---
name: citation-fact-check
description: 引用与事实核验：稿件论断与被引来源双侧逐字定位到页段并绑定全文/引句哈希，full/partial/none/unknown语义支持标签，版本更正撤稿离线状态闸，权限/原文失败可降级复核
---

# 引用与事实核验

核心不是“引用是否存在”，而是：**论断在稿件哪里、被引证据在来源哪一段、语义是否支持、来源版本和撤稿状态是否一致、他人能否按同一记录复跑。** 输出逐条问题、判定依据、严重度和修改建议；不代写综述、不润色、不替作者作最终研究结论。

## 输入、输出与依赖

- 输入：`/input/case.json`、`/input/task.md`、实际稿件与允许访问的来源；至少读取实际电子全文/扫描 PDF/摘要，不按 case 标签猜内容。
- 输出：尽早写 `/app/output/result.json`（先 partial，后增量完善）；保留原始 `output_contract` 全部字段和 `case_id`，可另附 evidence ledger。
- `/app/work` 保存合法取得的文本快照和 registry 元数据；不得保存无权限内容或伪称在线成功。
- `scripts/review_tool.py` 版本 `3.0.0`，仅 Python 3 标准库；命令退出码 0=通过，1=核验失败，2=调用/读取错误。

## 工作流与判对闸

### 0. 锁定稿件和来源版本

稿件文本按 `\f` 分页，空白行划段；记录稿件原文件和抽取文本 SHA-256。每条外部来源有稳定 `source_id`，记录实际取得的文本快照内容 SHA-256、DOI/URL、版本、出版/撤稿状态、访问状态、真实核验日期和状态证据 URL。**无来源全文时不能写“已核全文”。**

### 1. 显式覆盖六类与关键章节

六类：`fact/citation/design/statistics/argument/compliance`，以及 `sections.methods/results/discussion`（不同排版可映射到等价章节，在 notes 写明）。每项记录 `{status,notes,reason}`，状态为 `checked/not_applicable/pending/unchecked`；`checked` 必须写 checks，非 checked 写原因。**零 issue 不等于未检查。**

```bash
python3 scripts/review_tool.py coverage /app/output/result.json
python3 scripts/review_tool.py coverage /app/output/result.json --allow-partial  # 仅诚实部分交付
```

六类中至少覆盖：事实/数字一致性；引用完整/部分/不支持/未知；方法与结论适配；统计数值一致性；因果与范围论证；署名、重复发表、数据代码、伦理和利益冲突等适用规范。

### 2. 建立 claims 双侧证据账本

每条有外部引用的论断写入 `claims.json`：

```json
{"claims":[{
 "id":"C1","source_id":"R1",
 "claim_quote":"稿件中的连续逐字论断","claim_occurrence":1,
 "source_quote":"被引来源中的连续逐字证据","source_occurrence":1,
 "support":"full|partial|none|unknown",
 "support_rationale":"逐项比较方向、研究对象、样本、终点、条件和因果/相关范围"
}]}
```

`sources.json` 是本次实际快照清单（`path` 相对此清单目录，或测试时用 `text`）：

```json
{"sources":[{"source_id":"R1","path":"snapshots/R1.txt"}]}
python3 scripts/review_tool.py locate claims.json --manuscript manuscript.txt --sources sources.json
```

`locate` 同时查稿件和来源，输出页、段、`occurrence`、quote SHA-256、来源全文 SHA-256。归一化匹配只去空白并做 NFKC，不能改写词序或拼接两句。重复 quote 不默认取第一次，必须显式给 occurrence；输出 `ambiguous_quote_occurrence` 时回原文消歧。将实际返回的锚点写入 claims/issues，不再手填假定位。

无法取到某来源时：

```bash
python3 scripts/review_tool.py locate claims.json --manuscript manuscript.txt --sources sources.json --allow-partial
```

这只让**其他已完成部分**可交付，`complete:false`、对应 support 必须为 `unknown`，不能变 confirmed。

### 3. 引用—结论语义对齐（规则预警 + 人工语义判定）

| support | 定义 | 后处理 |
|-|-|-|
| `full` | 该引文直接支持当前论断的对象、方向、条件、终点和范围 | 保留双侧证据；不是仅题名相似 |
| `partial` | 只支持子结论，或强度/人群/条件更窄 | 必须关联 issue，拆分已被支持和外推部分 |
| `none` | 方向相反、数值/对象不符、来源不含该结论 | 必须关联 issue，引双方原句 |
| `unknown` | 无全文、严重歧义、来源/版本不足以判定 | 进入 uncertainty；不得猜支持 |

```bash
python3 scripts/review_tool.py align claims.json
python3 scripts/review_tool.py align claims.json --allow-unknown  # 允许unknown，但不视为完整
```

`align` 检查支持字段/理由，并用保守线索拦截 full 标签下的否定方向、全称/治愈外推、相关到因果、显式样本量冲突。**这是高精准预警，不是通用 entailment 模型**；通过仍须人工比较研究对象、干预、终点、时间和限定条件。partial/none 是合法审查结论，不会因存在差异被工具二次惩罚。

### 4. 来源版本、更正、撤稿与权限

保存带实际来源的 `registry.json`（离线快照，键为 source_id）：

```json
{"R1":{"canonical_doi":"10.xxxx/actual","current_version":"published-v2","publication_status":"published","retraction_status":"not_retracted","evidence_url":"https://实际状态证据"}}
python3 scripts/review_tool.py provenance sources.json --registry registry.json
```

`sources.json` 此时含 result 同构的来源元数据，不只文本路径。规则：
- DOI 与 registry 不一致、未披露版本/出版状态不一致、撤稿标记冲突均为 blocking；
- `version_difference_disclosed:true` 只有在报告明确交代预印本/正式版差异时使用，差异本身不自动判学术错误；
- `retracted` 必须有带 source_id 的关联 issue，严重度按它是否支撑核心结论判断；
- corrected/expression_of_concern 保留警告和状态证据；
- unknown、paywalled、permission_denied、unavailable 不能伪装为 `not_retracted` 或“全文已核”；必要时 `--allow-incomplete` 仅用于 partial。

本命令**不访问网络，只核带来的快照**；若环境有联网工具，实际查验并记录平台/出版方页面及访问日期，不能杜撰 registry 状态。

### 5. 缺陷类型和严重度

- `fact_error`：双侧原文可证实错误；`evidence_gap`：缺引用/缺材料/只部分支持；`source_version`：版本、撤稿、更正或出版状态问题；`norm_issue`：具名规范问题；`suggestion`：可选建议，只能 minor。
- `critical`：不可靠/不支持来源使核心结论不成立；`major`：重要论断仅部分支持、版本差异实质影响结论但可修复；`minor`：定位、格式、非关键表述或建议。
- `review_status=confirmed` 要求双侧证据已解析；`pending` 必须进入 uncertainty。撤稿不一律 critical，版本旧不自动判错，数据库无权限不能把未知写成无问题。

### 6. 异常处置（标识—恢复—降级）

| 题面异常 | 识别与恢复动作 | 输出边界 |
|-|-|-|
| 原文取不到 | locate/provenance 记录 source_id、路径/URL和实际 error；仅重试允许的来源/版本 | support=unknown，关联条目 pending，partial；不得引摘要虚构全文结论 |
| PDF 无法解析 | 记录文件哈希和抽取工具错误；可换环境声明的解析/OCR一次；扫描页单列 | 能读部分继续；未能读取的页/段进 unchecked；全文未读不得称 full-text checked |
| 引文严重歧义 | 参考文献号、DOI、作者年份均不足；重复 quote 报 ambiguous | 列候选 source_id/版本及 occurrence 候选，请求作者消歧；unknown，不默认第一篇/第一次 |
| 来源撤稿或版本不一致 | provenance 报 retracted/version_mismatch/status_mismatch | 撤稿必须关联 issue；披露实质差异；无法确定影响时 pending，禁假装已消除风险 |
| 数据库权限不足 | access=paywalled/permission_denied/unavailable，保留允许访问的摘要和元数据 | support=unknown 或明确仅限摘要范围；unchecked+uncertainty，partial；不能写“已查全文/未撤稿” |
| 图表或补充材料不可得 | 记录具体图/表/数据集条目 | 数字跨表一致性未查；不影响的其余类目继续 |
| 语言混杂 | quote 保留原语言，另行写翻译仅作解释 | 不用翻译串代替原文定位；否定词/限定条件由双语复核 |

### 7. 严格交付总闸

```bash
python3 scripts/review_tool.py schema /app/output/result.json   # 基础字段
python3 scripts/review_tool.py gate /app/output/result.json     # 最终必须运行
```

`gate` 强制校验：原 output_contract 保留清单、run/tool 版本、稿件和全部来源内容哈希、claims 双侧页/段/quote 哈希及其与注册全文哈希的对应、support 与 issue 链接、来源版本/撤稿字段、partial/none/unknown/pending 处置和严重度。正式 `gain` 无真实同输入对照就填 null，不造分数。

## result.json 字段骨架（非正式答案）

```json
{
 "schema_version":"3.0","case_id":"实际case_id","status":"issues|partial|pass|failed",
 "manuscript_version":{"label":"实际版本","sha256":"64位全文哈希","files":["实际文件"]},
 "run":{"tool_version":"3.0.0","run_id":"本次实际运行"},
 "contract":{"source":"/input/case.json#/output_contract","preserved_fields":["实际原字段"]},
 "claims":[{"id":"C1","source_id":"R1","claim_quote":"逐字论断","claim_locator":{"page":1,"paragraph":3,"occurrence":1,"quote_sha256":"…","source_sha256":"稿件全文哈希"},"source_quote":"逐字证据","source_locator":{"page":2,"paragraph":4,"occurrence":1,"quote_sha256":"…","source_sha256":"R1全文哈希"},"support":"partial","support_rationale":"只支持子结论"}],
 "sources":[{"source_id":"R1","role":"reference","doi":"10.x/xx","version":"published-v1","publication_status":"published","retraction_status":"not_retracted","checked_at":"真实日期","evidence_url":"实际URL","access":"open","sha256":"64位来源全文哈希"}],
 "issues":[{"id":"F1","claim_id":"C1","source_id":"R1","category":"citation","severity":"major","defect_type":"evidence_gap","review_status":"confirmed","location":"同claim定位对象","quote":"逐字论断","claim":"外推部分不受支持","fix":"限定结论","evidence":[{"source_id":"R1","quote":"逐字证据","basis":"来源仅覆盖子人群","locator":"同source定位对象"}]}],
 "categories":{},"sections":{},"checked_scope":{"did":[],"not_checked":[]},
 "gain":{"baseline_hit_rate":null,"skill_hit_rate":null,"false_positive_rate":null},
 "unchecked":[],"uncertainty":[],"change_log":[]
}
```

骨架中的字符串占位符须替换为实际对象/值；完整合法合成示例在 `bench/fixtures/good_result.json`。原 case 要求的其它字段原样保留。

## 自测与边界

```bash
python3 bench/bench_run.py
```

测试证据缺失/歧义/语义错标/撤稿/版本/权限等变异以及合法 partial、none、版本披露、显式消歧的零误杀。工具无法保证 OCR 完整、通用自然语言蕴含或实时撤稿数据库覆盖；这些边界必须进入 partial/uncertainty，而非补造结论。
