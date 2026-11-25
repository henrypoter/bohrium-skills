---
name: review-generation
description: 文献综述生成：先筛选再从文献归纳主题，逐条原文回链，显式呈现冲突与有界空白；适用于给定 PDF/题录/摘要集的可复核综述
---

# 文献综述生成（v2.0.0）

对实际输入跑完「筛选 → 主题归纳 → 证据组织 → 带引用草稿」。不承诺数据库全覆盖、全局召回率或单篇全文精读；不把“本次未检出”写成“该领域没有”。

## 调用与输入契约

- 读取 `/input/case.json`、`task.md` 及实际 PDF/题录/摘要；先查看 `environment/resources.yaml`，不得凭文件名猜论文内容。
- 工作文件放 `/app/work`；最终结果放 `/app/output/result.json`，并保存筛选表、证据表和综述草稿。
- 保留 `case.json.output_contract` 要求的全部原字段；下列字段是**附加审计字段**，不得替换原契约。缺失材料、无法判断、运行失败分别写入 `unchecked`、`uncertainty` 和 `status`。
- 纯标准库工具：`scripts/syn_tool.py`；无安装、无网络依赖。所有真实结论必须来自本次输入，不使用本仓库 fixture 充当正式答案。

尽早写出带 `case_id`、诚实 `status` 和当前限制的 partial 结果，再增量完善。`status=pass|issues|partial|failed`；存在未覆盖文献、接口失败或权限限制时不得标 `pass`。

## 判对工作流

### 1. 筛选协议先于写作，并逐条执行

先定义研究对象、时间窗、文献类型和可判定的纳排条件。每条 `screening_criteria` 有唯一 `id`；每条 `records[]` 填：

- `decision=include|exclude|pending`；
- `criterion_ids`：引用已声明判据，不能事后另造理由；
- `screening_reason`：该篇如何满足/违反判据；
- `fulltext_status=available|abstract_only|unavailable`；仅摘要不得假称看过全文。

`included`/`excluded` 与决定保持一致。重复文献保留 `duplicate_of`，并在 `duplicates[]` 写 canonical、重复 id 和 DOI/标题作者年等 `match_basis`；不能静默删重。`counts` 与原始记录、纳排和 pending 数闭合。

### 2. 建立可回看的证据行，再写论断

每条 `claims[]` 必须有 `id/text/theme/citations`，并区分：

- `claim_kind=material_fact|inference|unresolved`；推断另写 `inference_basis`；
- `certainty=established|suggestive|disputed|unknown`，强度不得超过原文；
- 每条 citation 写 `record_id/location/quote/support/evidence_strength`。`location` 到页、段、表或图，`quote` 是可直接核对的原文摘录，`support=supports|contradicts|context`，`evidence_strength=fulltext|abstract_only|indirect`。

实质论断只能引用 `included` 中记录。摘要/间接证据不得标 `established`。机检只能确认回链字段闭合；仍须逐条阅读原文判断其是否支持该句，不能把“有 citation”当成语义正确证明。

### 3. 主题从文献分布归纳，空白和冲突有锚点

- `themes[]` 写 `name/evidence/derivation/boundary`：`evidence` 是归成此主题的纳入记录，`derivation` 描述从哪些方法、对象或结论差异聚成，`boundary` 写明不包含什么。
- 所有纳入记录必须进入至少一个主题，或在 `unmapped_records[]` 说明不归类的理由；跨主题记录要在相关主题写 `overlap_note`。
- `conflicts[]` 并列至少两条 `claim_ids`，填 `resolution=unresolved|explained_by_methods|weighted` 和 `rationale`。若确实无冲突，填 `conflict_review.searched=true` 与检索说明，不能直接省略核查。
- `research_gaps[]` 以 `basis_claim_ids` 回链证据，标 `gap_type=evidence_absence|method_limit|conflict|search_limit`、`bounded_to_search=true` 和 `next_evidence`。没有空白时也须填 `gap_review`，禁止“未来应加强研究”式套话。

草稿按这些主题组织，每段能回到 claim id；反面证据与结论分歧并列呈现。

### 4. 版本与来源指纹

`run` 必填：

```json
{"case_id":"与顶层一致","skill_version":"2.0.0","tool_version":"2.0.0","input_sha256":"64位小写hex","generated_at":"实际UTC时间","source_snapshot":"输入快照标识"}
```

`sources[]` 对每条原始记录（包括排除项）登记 `{record_id,path,sha256}`；`path` 相对 `--source-root`，SHA-256 根据实际文件字节计算。只有摘要时也给实际摘要/题录文件建来源，不补造 DOI、年份或全文。

## 必过机检闸

在提交产物前依次运行，任一退出码非 0 就修复或诚实降级：

```bash
python3 scripts/syn_tool.py schema /app/output/result.json
python3 scripts/syn_tool.py screen_check /app/output/result.json
python3 scripts/syn_tool.py cite_check /app/output/result.json
python3 scripts/syn_tool.py evidence_check /app/output/result.json
python3 scripts/syn_tool.py theme_check /app/output/result.json
python3 scripts/syn_tool.py grounding_check /app/output/result.json
python3 scripts/syn_tool.py provenance_check /app/output/result.json \
  --input /input/case.json --source-root /input
```

| 命令 | 硬约束 |
|-|-|
| `screen_check` | 每篇决定均引用有效判据；重复、纳排集合和计数闭合 |
| `cite_check` | 无论断漏引、无悬空引用、无缺 location，纳入项有筛选理由 |
| `evidence_check` | 引用属于纳入集，具有原文摘录、支持关系和强度；事实/推断/未定分开 |
| `theme_check` | 声明主题均有带引用论断，论断不落入未归类项 |
| `grounding_check` | 主题有归纳依据和边界，覆盖纳入集；冲突与空白有证据锚点 |
| `provenance_check` | 版本字段齐全，实际重算 case 与每份来源 SHA-256 一致 |
| `schema` | 原交付字段之外的审计字段、状态和计数通过初检 |

## 异常处置表

| 异常 | 必须动作与输出状态 |
|-|-|
| 缺全文 | 标记 `abstract_only/unavailable`；仅摘要可作有限筛选，不能作全文页码或 established 论断；不可判进 `pending/unchecked` |
| 元数据不全 | 字段标 `unknown`，保留实际来源和缺失项；不得猜 DOI、年、作者、期刊 |
| 文献重复 | DOI 优先，其次标题+作者+年；保留 canonical、重复 id、匹配依据，重复项 exclude 且计数闭合 |
| 结论冲突 | 正反 claim 与原文并列，检查对象/方法/数据差异；无依据时 `unresolved`，不得抹平 |
| 超出上下文 | 分批筛选和抽取，记录已覆盖 record id；未覆盖部分进 `unchecked`，状态至少 `partial` |
| 检索为空 | 保留检索式、范围与零命中；区分零命中和全文不可得，放宽检索须另留日志；不得推出“无人研究” |
| 接口异常/解析失败 | 记录失败文件、错误和已成功部分；可重试一次或换已提供解析器，失败进 `unchecked`，状态降级 |
| 权限不足 | 不绕过访问控制；用可合法访问的摘要/题录并标限制，不能声称读完全文 |

## result.json 附加字段速览

```json
{"case_id":"","status":"partial","research_question":{},"run":{},"screening_criteria":[],
 "records":[],"included":[],"excluded":[],"duplicates":[],"claims":[],"themes":[],
 "unmapped_records":[],"research_gaps":[],"conflicts":[],"counts":{},"sources":[],
 "gain":{},"unchecked":[],"uncertainty":[],"change_log":[]}
```

平台若提供基础 Agent 对照，`gain` 记录同输入、同预算下的引用覆盖率、悬空引用数、人工修复数及原始轨迹位置；未实际运行就填 `null` 并说明，禁止编增益。

## 最小合成调用示例（非正式案例结果）

`bench/fixtures/` 是接口测试材料，不是科研答案：

```bash
python3 scripts/syn_tool.py screen_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py evidence_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py grounding_check bench/fixtures/good_result.json
python3 scripts/syn_tool.py provenance_check bench/fixtures/good_result.json \
  --input bench/fixtures/case.json --source-root bench/fixtures/sources
python3 bench/bench_run.py
```

示意输出：`{"ok": true, ...}`；测试末尾为 `total 18/18`。正式运行必须用 `/input` 的实际案例重新生成所有内容、时间与哈希。
