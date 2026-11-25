---
name: systematic-review
description: 可复核的系统性文献综述：预注册检索与纳排标准、去重和双人筛选、质量评价、逐字原文回链、冲突/空白矩阵及公平基线增益审计。适用于提供文献/检索结果的实际系统综述任务。
---

# 系统性文献综述（可复核流程 v2.0.0）

把实际输入变成一条他人能重走的链：**问题拆解 → 可执行检索 → 标准预注册 → 去重/两轮筛选 → 质量评价 → 主题归纳 → 冲突与研究空白 → 综述**。

不声称在线数据库全局覆盖、真实领域绝对新颖性或全文精读/翻译能力。不能用本 Skill 的模板、示例或领域标签替代原论文事实。工具验证结构、计算、哈希和逐字匹配；**语义相关性、质量偏倚与引文是否真正支持论断仍由 Agent 依据原文判断**，不能由脚本代判。

## 1. 输入、输出与依赖

- 实际输入：`/input/case.json`、`/input/task.md` 及题面提供的数据库结果、原文或其他材料。先列目录并读取实际文件，保留原 `output_contract` 全部字段和 `case_id`。
- 工作区：`/app/work`；交付：`/app/output/result.json`、筛选记录、证据矩阵、质量评价、综述及任务要求的其他产物。
- 交付首部字段：`schema_version: "2.0.0"`、`skill_version: "2.0.0"`、`case_id`、诚实 `status`、带输入哈希和检查点的 `run`。
- 运行依赖：Python 3 标准库，无安装、无网络、无第三方包。平台已有 PDF 解析器可用于生成 UTF-8 抽取文本；本工具负责核验哈希与引文，不假装自行解析 PDF。
- 下例中 `$SKILL_ROOT` 是实际安装目录（通常为 `/skills/weekly-skill`），`$OUT` 是 `/app/output`。所有命令返回单个 JSON；0=通过，1=未通过，2=调用错误。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" --version
python3 "$SKILL_ROOT/scripts/syn_tool.py" hash /input/case.json /input/task.md paper.pdf
```

尽早保存带全部必需字段的 partial 结果，再逐步改善。未知值用 `unknown`、`null` 或空数组并加入 `not_checked`；不要猜 DOI、年份、样本量、检索命中数、模型请求数或运行时间。效率指标未知时填 `null` 并在 `run.metric_notes.<字段>` 写明原因。

## 2. 必须按顺序执行

### A. 锁定输入与恢复点

1. 对 `case.json`、`task.md`、每篇原文和对应抽取文本计算 SHA-256，写入 `run.input` 与 `records[].source`。
2. `source` 必须有 `path/sha256/text_path/text_sha256/extractor/extractor_version`。抽取文本是定位载体，原文哈希用于锁定版本；引用须用 `source_sha256` 回指原文。
3. `run.checkpoints` 逐步记录 `completed/pending/failed/skipped` 和 `output_path`，使中断能定位，而非只写“运行失败”。

### B. 先定方案和标准，再看判定结果

1. 把问题拆为 `research_question.elements`，记录概念、同义词、受控词、术语歧义及 PICO/其他框架。
2. `search.databases` 写实际数据库/本地语料、接口与字段；每条 `search.queries` 保留**完整检索式**、布尔逻辑、字段、同义词意图、时间/语言限制、实际运行时间和真实 `result_count`。不能只交一个关键词串。
3. `screening_criteria` 每条包含：`id/type/stage/criterion/operational_test/priority/reason_code/effective_version`。标准须可判定，覆盖对象、研究设计、时间、语言、全文条件；“相关/合理”不是操作条款。
4. 在任何判定前定稿 `protocol.version/created_at/conflict_policy`，将标准数组的规范化 SHA-256 写入 `criteria_sha256`。以后修改必须升版本、写 `change_log`，并用对应版本重筛，不能静默放宽。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" protocol_check "$OUT/result.json"
```

### C. 去重、两轮筛选与分歧裁决

1. 在 `duplicates` 记录 survivor、duplicate IDs、规范化方法和值、双方字段证据。DOI 规范化相同可合并；无 DOI 时用规范化题名+第一作者+年并人工核对。只对“题名相似”不得合并。
2. 每条原始记录在 `decisions` 留痕：去重轮、题录轮、必要时全文轮；每次判定写 `record_id/stage/decision/reviewer/protocol_version/criterion_ids/reason_codes/decided_at`。
3. **每篇纳入和排除都要理由码及原文证据**，不能只给排除项理由。`evidence` 含逐字 `quote/quote_sha256/source_sha256` 和 `location`。排除取最高优先级且最具体的预注册条款，不堆无关码。
4. 双人分歧不得覆盖旧判定：新增 `resolves_disagreement: true` 的裁决，并在 `adjudicates` 链接双方 decision IDs。
5. `included/excluded` 由终判重算；`counts` 满足：
   - `records_raw = records_unique + duplicates`
   - `records_unique = included + excluded + undecided`

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" screen_check "$OUT/result.json"
```

### D. 纳入研究逐维质量评价

选择适合研究设计的量表，在 `quality_scales` 固定版本、维度提示、判断到分数映射、总等级阈值。每个纳入研究在 `quality_appraisals` 中：

- 每个维度都有判断及逐字证据/精确定位，不能只写“质量较高”；
- `overall.score/max_score/normalized_score/rating` 必须能由量表重算；
- `impact_on_synthesis` 和 `claim_ids` 说明质量如何限制降级或结论，不把低分研究静默删除。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" quality_check "$OUT/result.json"
```

### E. 论断—引用—原文三级闭环

每条实质论断有稳定 `id/text/kind/theme/citations`，并区分：

- `material_fact`：材料直接报告的事实；
- `inference`：合理推断，另写 `inference_rationale` 与适用边界；
- `uncertain`：无法确定，另写 `uncertainty`，不得改成肯定句。

每条引用须满足：

1. `record_id` 在文献清单且在最终纳入集；排除文献只能用于筛选/排除证据，不能偷偷支撑综合结论。
2. `location` 精确到 `page + paragraph + sentence`，或结构化材料的具体 `field`。`"结果第3段"`、`"p.1"` 不合格。
3. `quote` 为原文逐字片段；`quote_sha256` 是该片段 UTF-8 的 SHA-256；`source_sha256` 与记录原文一致。
4. `support` 标为 `direct/partial/contradicts`。部分支持要收窄论断，反对证据进入冲突矩阵。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" cite_check "$OUT/result.json"
python3 "$SKILL_ROOT/scripts/syn_tool.py" quote_check "$OUT/result.json"
```

`quote_check` 会重算原文与抽取文本哈希，并在对应文本中查找逐字引文（允许仅空白/换行差异）。自洽地伪造哈希但原文无此句仍失败。

### F. 主题后归纳、冲突并列、空白有排除证据

- 先读证据并编码论断，再形成 `themes`。每主题的 `derived_from` 必须等于其论断实际引用的文献集合，`claim_ids` 双向一致，`induction_note` 说明聚类依据。不能先套固定主题。
- 纳入证据互相矛盾时，`conflicts` 保留至少两端定位，`support` 同时出现 `direct/contradicts`，记录可能解释、是否解决及对论断影响。只有一篇纳入研究时，把研究间冲突列为 `not_checked`。
- `research_gaps` 分为：
  - `evidence_of_absence`：回链真实 query IDs、因此被排除的 record IDs、实际 reason codes 和受影响 claims；只能声明题定边界内“未获得可纳入证据”。
  - `search_limitation`：回链 queries 并说明未覆盖范围；这是检索局限，不是“已证明不存在”。
  - `unchecked`：填写原因并进入 `not_checked`。
- 研究空白不可由“我没找到”单独推出；必须区分排除证据与检索遗漏。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" theme_check "$OUT/result.json"
python3 "$SKILL_ROOT/scripts/syn_tool.py" synthesis_check "$OUT/result.json"
```

### G. 异常识别与处置闭环

每次实际异常在 `exceptions` 写 `type/signal/action/status/affected_ids/disposition`。pending 不得交 `pass`，应写 issues/partial 并定位受影响步骤。

| 题面点名失败 | 识别信号 | 必须采取的具体动作及输出 |
|-|-|-|
| 检索为空 | `result_count=0` | 核对字段/拼写/同义词/时间限制，保存原式；分类 `no_evidence_in_scope/overly_restrictive/not_checked`，记录放宽式及 follow-up IDs；空白仅限检索边界 |
| 数据库或接口超时 | `query.error.type=timeout` 或读取失败 | 保留查询和检查点；在预算内按原式重试并写 `retry_evidence`，仍失败则降级到已提供材料、标 partial，命中数/结果不得补造 |
| 全文不可得 | `availability.full_text=false` | 仅摘要足以触发明确排除条款时才排除并标 `degraded`；否则 `undecided + not_checked + human_review`，不做全文质量或疗效判断 |
| 术语歧义 | 同概念多写法/缩写、受控词冲突 | 建同义词与受控词映射，用 OR 更新并实跑检索式，新增 query ID；在异常中列出受影响概念，不静默选一个词 |
| 纳排条款冲突 | 同记录命中互斥条款或双人结论相反 | 按预注册优先级处理，新增具名裁决并链接原 decision IDs；版本化修改标准后重筛，保留 change_log |
| 纳入证据互相矛盾 | 同问题出现 direct 与 contradicts | 建冲突矩阵，保留两端逐字定位；比较设计/人群/偏倚，未解决则并列呈现并收窄结论，不投票掩盖 |
| 权限不足 | 读取拒绝/缺少访问权 | 停止受影响读取，不绕过权限；登记 denied 文件/接口并交人工，checkpoint 标 failed，输出 partial/failed，不伪写哈希或内容 |

补充：重复文献按 C 节留去重依据；元数据缺字段填 `unknown`；超长输入按检索批次/记录分块并汇总真实覆盖数；中断按最近 completed checkpoint 恢复。

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" exception_check "$OUT/result.json"
```

### H. 同输入基础 Agent vs 本 Skill 对照

只有平台提供或实际生成双方结果时才计算增益。双方必须 `case_id`、case/task SHA-256、permissions 完全相同。将基础结果路径传给：

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" gain_check "$OUT/result.json" \
  --baseline /path/to/baseline-result.json --update
python3 "$SKILL_ROOT/scripts/syn_tool.py" gain_check "$OUT/result.json"
```

`--update` 从双方原始记录重算并写入 `gain`：论断引用覆盖率、可解析引用率、可核验引文率、筛选理由完整率、质量评价覆盖率、有证据空白率、耗时、请求数、人工返工项及差值；注明指标边界。无基线时 `gain.comparison_status="not_available"` 并写 `reason`，**禁止用示例数值冒充实测增益**。

## 3. 最终总闸门

```bash
python3 "$SKILL_ROOT/scripts/syn_tool.py" audit "$OUT/result.json" \
  --baseline /path/to/baseline-result.json \
  --case /input/case.json --verify-artifacts
```

无可用基线的诚实 partial 运行使用 `--allow-gain-not-run`，报告会保留 `gain_not_run` 到 `not_checked`。产物路径/哈希、原始 output_contract、输入身份、全部计数、引文、异常与质量计算任一失败都不得声称“机检全绿”。缺失环节写 `not_checked`，未判断写 `undecided`，运行失败用 `failed` 并定位 checkpoint；三者不可混用。

## 4. 输出结构与复用资源

完整、可运行且仅作接口演示的合成最小例：`examples/minimal/result.example.json`；对应合成基础结果仅用于验证对照计算，不是真实 Agent 成绩或正式案例答案。核心顶层字段：

```text
schema_version, skill_version, case_id, status, run,
research_question, search, protocol, screening_criteria,
records, decisions, duplicates, included, excluded, counts,
quality_scales, quality_appraisals, claims, themes,
conflicts, research_gaps, exceptions, sources, artifacts,
gain, unchecked, not_checked, uncertainty, change_log
```

可复用模板：`templates/protocol.md`、`templates/screening_table.md`、`templates/quality_scale.md`、`templates/evidence_table.md`、`templates/review.md`。使用与维护说明见 `docs/README.md`；异常字段定义见 `docs/EXCEPTIONS.md`。

自测（仅合成夹具）：

```bash
python3 "$SKILL_ROOT/bench/bench_run.py"
```

交付底线：标准先于筛选、每篇纳排有条款/理由码/逐字依据、去重可重算、质量逐维可复算、每个综合论断回链纳入原文、主题由实际引用归纳、冲突不消失、空白有排除证据、失败有处置、版本与产物哈希可复跑。
