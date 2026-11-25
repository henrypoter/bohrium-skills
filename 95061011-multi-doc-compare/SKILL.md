---
name: multi-doc-compare
description: 多文档比较与整合 Skill v4。读取 /input/comparison-workorder.json 与语料，按共同字段、caliber 六维和四态证据卡构建比较矩阵；硬检逐段引文与跨文档错位，执行主题/版本排除、不可读图表取样和无法归因冲突审计；不可比禁合并，缺失不投票。输出带 run_id、材料哈希、输入/输出清单和异常边界的 result.json，适用于 2~15 篇论文。
---

# multi-doc-compare：多文档比较与整合（v4）

核心原则：**对得齐**（同一套字段定义）、**填得准**（取值随附单位/口径/条件）、**说得清**（一致/分歧/互补显式区分，分歧必归因）、**查得回**（每格与差异结论回到具体段落）。字段、口径、四态、归因枚举的完整定义见 `templates/field_dictionary.md`。

## 0. 预算纪律（硬约束）

- 平台预算：64 次模型请求 / 900 秒 / 单次响应 ≤16384 tokens。**自律线：每案例 ≤12 请求、≤600 秒**。
- **先写诚实 result.json，再增量改进**：阶段 1 先写保底盘；预算逼近上限即停止新分析，把已有部分定稿。
- 长内容一律用脚本写入 /app/work 文件，不要在回复里整段转储。

参考请求分配（N=文档数）：阶段1 清点+保底 ≤1；阶段2 抽卡 ⌈N/2.5⌉（每请求 2~3 篇，N>8 压到 ≤4）；阶段3 矩阵+可比性 1~2；阶段4 关系+归因 1~2；阶段5 校验定稿 1；余量 ≥2。

## 1. 输入识别（阶段 1）

1. 读 `/input/case.json`、`/input/task.md`、`/input/comparison-workorder.json`。取出：研究问题、目标论文集合、**比较维度列表**、**output_contract 全部字段名**（逐字保留）。
2. PDF 用环境预装 pdf-text 工具（见 environment/resources.yaml）转纯文本存 `/app/work/text/<doc>.txt`；文本直接复制。**解析失败的文档记入 warnings，不得编造内容。**
3. 运行 `python3 scripts/index_corpus.py --text-dir /app/work/text --out /app/work/corpus_index.json`（可选 `--map ids.json` 映射工单 source_document_id），得到稳定 `DOCID::pNNN` 段落索引；每篇附 `content_sha256/content_bytes`，索引带 `index_version`。
4. 在 `/app/work/case_meta.json` 保存 `case_id/status/contract_fields/uncertainty/change_records`，并写两个异常边界：`document_assessments[]={source_document_id,relevance:relevant|irrelevant|uncertain,version_state:selected|only|superseded|duplicate|unknown,reason,paragraph_id}`；`visual_gaps[]={source_document_id,figure_id,reason}`。不相关/版本排除和 uncertain 必须有同文档段落定位；**语义判断由 Agent 做，脚本只验证边界不代替主题分类**。
5. 立刻写保底 `/app/output/result.json`：status="partial"、case_id、output_contract 全字段（未完成置空并注明）、uncertainty 记“分析进行中”。

## 2. 逐文档证据卡（阶段 2）：口径 + 四态

按字段字典逐篇抽卡，追加写 `/app/work/evidence_cards.jsonl`（每行一张卡）：

```json
{"source_document_id":"P1","field":"metric_value","value":"92.4","unit":"%","context":"甲基橙 20 mg/L, 可见光 60 min","paragraph_id":"P1::p014","quote":"原文短句≤40字","confidence":"direct|inferred","value_state":"reported-positive","caliber":{"task":"光催化降解","metric":"removal rate","unit":"%","object":"methyl orange 20 mg/L","condition":"visible light 60 min","budget":"catalyst 0.5 g/L"}}
```

规则：
- **取值必须来自它标注的那篇文档**；quote 为原文片段（可截断），须在所标 paragraph_id 内逐字命中（NFKC+去空白归一化）；段落归属也须匹配该 source_document_id。跨文档借定位/借引文是硬错误。
- **四态 `value_state` 必填**（reported-positive / reported-negative / not-applicable，定义见字典）。**未报告 = 不抽卡**，脚本自动列入 gaps；缺失绝不参与投票（机检告警）。
- **口径 `caliber`**：metric_value 卡必填，六维子集 task/metric/unit/object/condition/budget，metric、object 非空。**取值归一化**（单位规范简写、指标规范小写名）——脚本按归一化字符串机检跨文档口径差异。
- 图表读数：`source_kind="figure"`、`figure_id` 必填，confidence="inferred"，note 写“图 X 读数，近似”。图不可读时只在 visual_gaps 记录并保留字段缺口；**若仍出现该 figure_id 的证据卡，audit exit 1**。
- 同一论文多版本：只用工单指定版本（无指定用最新版），其余标 superseded/duplicate 并排除，记入 change_records；任何关系引用被排除版本即硬错误。

## 3. 对齐矩阵与可比性判定（阶段 3）：判定留痕

证据卡按 字段×文档 排成矩阵；对工单可比性维度（默认 task、metric、units、material、pollutant、budget，工单优先，映射到六维）逐组判定，写 `/app/work/relations.json`：

- `comparable`：口径一致，可定量对比；填 `score`（六维对齐维数）；
- `comparable_subset`：仅子集内可比，**必填 `subset`**（边界，如“仅同一染料甲基橙”）；
- `noncomparable`：口径不同，**必填 `blocking_dims`（阻断维度清单）+ ≥10 字理由**；双边取值保留，禁合并/平均/排名；
- `unreported`：某文档未报告该维度，列入缺口。

relations.json 记录示例见 `examples/minimal_example.md`。脚本机检：对涉事证据卡 caliber 的 unit/metric 维归一化比对——发现差异却标 comparable、或 blocking_dims 漏掉机检差异维度，validate 记告警 issue（exit 0，不阻断）。**单位可换算时先换算并在 explanation 写明过程（含维度名），再判 comparable。**

## 4. 结论一致性与分歧归因模板（阶段 4）

对每个结论维度在 relations.json 追加：`consistent`（方向与强度一致）/ `partially_consistent`（方向一致、强度/范围异）/ `conflicting`（方向相反或互斥）/ `complementary`（覆盖不同方面）。

**conflicting 归因模板（脚本机检）**：`attribution` ∈ sample/method/condition/metric/unit/unattributable（必填）；`explanation` ≥10 字写清差异来自哪个条件的哪个取值，unattributable 时 ≥20 字记录排查过程；`evidence` 覆盖 ≥2 篇涉事文档。无法归因必须再加 `resolution_status="unresolved"` 与 `checked_dims`，后者至少覆盖 sample/method/condition/metric/unit；标成 resolved 或漏排查字段即硬错误，result.uncertainty 自动保留未解决冲突。

**投票纪律**：consistent/partially_consistent/conflicting 列出的每篇文档，evidence 里必须挂该文档真实存在的证据卡段落——脚本据此记告警“缺失当否定”。不可比数据集/染料不得合并成单一数值结论。

## 5. 校验与定稿（阶段 5）

```bash
python3 scripts/intake_audit.py audit --work /app/work            # 独立异常边界硬闸；写 document_audit.json
python3 scripts/validate_and_render.py validate --work /app/work   # 引文/定位/字段校验，并再次执行异常审计
python3 scripts/validate_and_render.py render   --work /app/work   # 排除越界文档后渲染矩阵/判定/归因/告警
python3 scripts/validate_and_render.py result   --work /app/work --out /app/output
```

validate 分两类：**硬错误（exit 1，须修正复跑）**＝JSON/字段非法、定位不存在或跨文档、quote 不在所标段落、metric_value 缺 unit/caliber，以及越界文档参与关系、不可读 figure_id 被取样、unattributable 冲突被标 resolved/未记录排查维度；**判定缺陷（告警 issue，exit 0）**＝强行合并/口径冲突、noncomparable 缺 blocking_dims、缺失当否定、一般分歧未归因，进入 validation_report.issues 与矩阵告警。输出仍须诚实 partial，不能因可导出就隐藏硬错误。
`result.json` 含原 output_contract、case_id/status/status_reason、sources、uncertainty、coverage/relations/gaps、validation_errors/issues/change_records，并新增 `schema_version/skill_version/run_id`、`document_audit`（excluded_documents/visual_gaps/unresolved_conflicts）、每篇 `content_sha256/content_bytes`、`input_artifact_manifest/output_artifact_manifest`；同时复制索引、关系、证据卡、矩阵和两份报告，便于独立复算。run_id 由 case_id 与输入文件摘要确定，不虚构模型、服务或测评版本。

## 6. 异常处理

| 异常 | 处置 |
|-|-|
| PDF 解析失败 | warnings 记录文档与原因；未抽取字段列 gaps(reason=unreported)，status 至多 partial，继续其他文档 |
| 图表无法读取 | visual_gaps 记 doc+figure_id+unreadable/parse_failed；不得估值、不得从相邻曲线外推，figure_* gap 留底；同图取样触发硬错误 |
| 某文档缺某维度 | 不填值、不推测、不投票，列入 gaps(reason=unreported) |
| 条件/单位/材料/数据集/染料不同 | noncomparable + blocking_dims + 理由，双边原值/单位/条件保留，禁止合并 |
| 论文主题不相关或无法确认 | assessments 标 irrelevant/uncertain + 同文档段落证据 + 原因；矩阵和关系排除，audit 引用即失败 |
| 同一论文多版本 | 用工单指定版本；superseded/duplicate 不进入关系，选择过程写 change_records |
| 结论矛盾且无法归因 | conflicting + unattributable + resolution_status=unresolved + checked_dims + 双方证据；写入 uncertainty，禁止包装成一致结论 |
| 机检告警（口径实同而表述异） | 统一 caliber 规范写法减少噪声；告警不阻断定稿，issue 留档供复核；硬错误不得降级成 issue |
| 预算逼近上限 | 停止新分析，用当前 /app/work 跑 audit/validate/render/result 定稿（诚实 partial） |

## 7. 资源清单与复用

- `scripts/index_corpus.py`：纯标准库，段落索引与材料内容摘要（index_version 2.0.0）。
- `scripts/intake_audit.py`：纯标准库 `audit --work`，主题/版本排除、不可读图表复用、无法归因冲突的独立硬闸。
- `scripts/validate_and_render.py`：纯标准库 validate / render / result（v4.0.0），逐段引文校验、口径/归因机检、版本化产物与摘要清单。
- `templates/field_dictionary.md`：字段字典 + caliber 六维 + 四态 + 归因枚举，可搬到其他论文集合。
- `examples/minimal_example.md`：最小调用示例（合成材料，非正式案例结果）。

适用范围：同一研究问题下 2~15 篇科研文档；工单维度优先。限制：不自动读 PDF（依赖环境 pdf-text）；语义可比性由模型判定，脚本机检定位真实性、口径一致性与归因完整性。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/read_tool.py support_check answers.json --text source.txt` 把每条证据引文在原文里做逐字匹配，不在原文的（误报）直接揪出；支持度分档统计。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：证据逐字回链、支持度分档。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/support_rubric.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/support_rubric.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py          # 全部正向零误杀 + 变异必命中（17 项）
python3 bench/bench_intake_audit.py # 仅跑新增异常/定位/版本字段硬闸（10 项）
```
