---
name: research-translation-writer
description: 面向科研成果转化写作的“受众画像→证据取舍→术语锁定→论断边界→多文体成稿→逐段复核”闭环。适用于把论文、技术报告或事实底稿改写为公众科普、项目材料、双语摘要或结构化稿件，并要求数字/单位/样本/限定条件/图表/引用可回溯、改动可接受或拒绝时触发。纯标准库 scripts/transfer_check.py 提供原文逐字回查、来源定位、保留项与事实漂移机检。
---

# 科研成果转化写作：完成产物，也保留来源

## 1. 适用范围与交付

**聚焦问题**：同一科研材料转为面向不同读者的成稿时，防止“为了易读而删证据、为了有说服力而拔高结论”。

输入为 `/input/case.json`、`/input/task.md` 及实际论文/底稿/图表/统计材料；不依据文件名或领域标签猜事实。输出到 `/app/output`：

- `transformation.md`：满足指定受众、体裁、篇幅的可编辑干净稿；
- `transformation_review.md`：内容相同但保留 `[S#]` 来源标记的复核稿；
- `evidence_project.json`、`evidence_report.json`、`audit_report.json`：证据、原文定位和机检报告；
- `result.json`：`case_id`、`output_contract` 全字段、主结果、来源、逐段改动、异常、不确定性和 `gain`。

若 task 指定其他文件名或格式，以 task 为准，同时保留上述审计信息。示例和 bench 都是自拟回归材料，**不是正式案例答案**。

## 2. 环境与预算

- 仅需 Python 3 标准库；无 pip、网络或共享核心依赖。Skill 安装目录通常为 `/skills/weekly-skill`。
- 每案例建议不超过 12 次模型请求、600 秒。素材清点、证据回查、机检与格式比较不耗模型请求。
- **先写 partial 再改进**：读完 case 后立即写 `/app/output/result.json` 骨架，包含 output_contract 全字段；之后增量覆盖，运行中断也保留诚实部分结果。
- 长文分章建立证据和改写，不在一次响应中塞入全文；每章落盘后再继续。

```bash
T=/skills/weekly-skill/scripts/transfer_check.py
[ -f "$T" ] || T=<submission目录>/scripts/transfer_check.py
```

## 3. 端到端流程（必须按序闭环）

### A. 读取约束，先区分三类失败

1. 从 case/task 抄录 `case_id`、受众知识背景与阅读目的、目标体裁、渠道、语言、篇幅上下限、指定小节、输出字段。
2. 遍历并读取实际材料。PDF 若有预装 `pdftotext`，保留分页提取文本到 `/app/work/sources/`，project 的 `source` 指向提取文本并另记原 PDF/页码；无提取工具或扫描件不可读时，不猜数，记材料缺失/不可读。
3. 先写 partial result。**材料缺失**（文件/引用没有）、**无法判断**（材料存在但证据不足或互相冲突）、**运行失败**（解析/工具异常）分开记录，不能统称“无法完成”。

### B. 建证据底账：先回原文，后写稿

复制 `templates/transfer_project.json` 为 `/app/work/evidence_project.json`。每个关键结论、数字、样本、限定条件、方法、图表和引用各建一条：

```json
{"id":"S1","kind":"number","fact_key":"accuracy",
 "source":"sources/paper.txt","line":18,"quote":"含数字与限定条件的原文整句",
 "surfaces":["88.1%","120 名"],"required":true,"strength":"preliminary","figure":"图1"}
```

硬规则：

- `quote` 必须逐字来自实际材料；`line` 或 `field` 必须能定位。只允许规范空白差异，不能“凭意思引文”。数字的 `surfaces` 必须是 quote 的逐字片段，**值和单位一起抄**，不心算换算。
- `required=true` 用于必须保留项：关键结论、样本信息、指标口径、比较基准、限定条件、方法要点、相关图表与引用。可压缩/可删除项也登记，删除理由进入 changes。
- `strength` 取 `established/observed/preliminary/association/observational/not_significant/uncertain`；相关与初步结果不能升级为因果或定论。
- 同一事实的冲突值使用同一 `conflict_group`；只有人工确认后在 `resolutions` 写 `status=human_confirmed` 和 `chosen`，不得自行挑选好看的值。
- 建术语表：`canonical` 唯一说法、`aliases` 禁用别名、`abbreviation/expanded` 首次展开、`plain` 面向公众的固定白话解释。

运行证据闸，**任何 fail 未修复不得据此起草**：

```bash
python3 "$T" evidence /app/work/evidence_project.json /app/work/evidence_report.json
```

### C. 受众画像 → 内容取舍 → 文体映射

复制 `templates/brief.json`，把 task 的要求变成机检字段。然后决定：

| 层级 | 必须做什么 | 不得做什么 |
|---|---|---|
| 读得懂 | 首次缩写展开；公众稿加入 plain 解释；句式与例子服务阅读目的 | 不展开缩写、用新行话解释旧行话 |
| 留得住 | 所有 required 项进稿；保留样本、单位、基准、条件、图表和引用 | 把限定条件、阴性结果、样本信息当冗余删除 |
| 说得准 | 句末挂 `[S#]`；论断强度匹配 strength；同概念只用 canonical | 相关写成因果、初步写成定论、无依据新增数字 |
| 接得住 | 每段一条 changes：原位置、改后全文、动作、理由、证据 id | 只交无法回填的改写建议或无记录整篇覆盖 |

按 `templates/genre_skeletons.md` 选择科普/项目/双语/结构化骨架，不强行套 Results & Discussion。篇幅与体裁冲突时先保留 required 证据，压缩背景和重复表述；仍冲突则 partial 并请求人工取舍。

### D. 完成整篇复核稿与逐段改动账

- 在 `/app/work/transformation_review.md` 写**完整可用成稿**，不是建议、提纲或片段。来源可写“句。[S1]”或“句[S1]。”。
- 在 project 的 `changes` 为每个正文段记录：`before_quote`（keep/revise/delete 必填且回原文）、`draft_segment`（非 delete 必填且逐字命中新稿）、`action`、`reason`、`evidence_ids`。
- 纯新增衔接句用 `action=add`，但仍需理由；事实性新增必须有材料证据。删除必需项会被 retention 拦截。

### E. 成稿机检，修复后再跑

```bash
python3 "$T" audit /app/work/transformation_review.md \
  /app/work/evidence_project.json /app/work/brief.json /app/work/audit_report.json
```

`audit` 的 fail 均为交付阻断项：

1. 必须保留项缺失、悬空来源、含数字句无来源；
2. 数字或单位不是本句所引证据的逐字表面形式、图表漏引；
3. 相关/观察证据因果化、初步/不确定证据定论化、不显著写成显著；
4. 禁用别名、首次缩写未展开、公众稿缺白话解释、未声明缩写；
5. 缺指定体裁小节、篇幅越界；
6. 段落无改动记录、改前引文回不到原文、改后段定位失败；
7. 涉密/未发表材料缺不外传和人工审批标记，或公开渠道未获发布批准。

修复的是稿件或底账，不得为消告警而放宽规则。warn 逐条写 uncertainty；有 fail 或未裁决冲突时 status 保持 partial。

### F. 干净稿、复核稿和 result 同步定稿

1. 从 review 稿**仅移除 `[S#]` 标签**生成 `/app/output/transformation.md`，不借机改字；review 稿也复制到 output。用 diff 确认差异仅为标签，来源映射留在 result。
2. 将 evidence/audit 报告复制到 output；`result.validation` 写 `fail` 和 `evidence_fail` 实际计数。
3. `sources` 保留 `draft_segment→evidence id→resolved_source→actual_lines→quote`；`changes` 保留逐段 before/after/reason；`uncertainty` 保留材料缺口、冲突、未确认内容。
4. 用 `result` 闸检查契约、文件存在、complete 闭环和 gain；case 的 output_contract 字段一个不能少：

```bash
python3 "$T" result /app/output/result.json /input/case.json /app/output/result_report.json
```

## 4. 同输入同权限增益记录（不编造白板）

`result.json.gain.protocol` 固定声明 `same_input/same_constraints/same_permissions/same_budget=true`。平台提供基础 Agent 结果时，双方计算同一输入 SHA-256，填 `comparison_status=completed`、两侧 metrics 和证据路径；至少比较 `fact_errors`、`terminology_errors`、`required_missing`、`manual_edit_items`、`rework_rounds`、`evidence_coverage`。

平台未给 baseline 时写 `comparison_status=pending_platform`、`baseline=null`，不得拿自拟 bench 冒充平台成绩。`bench/bench_results.json` 的 `local_fixture` 仅证明确定性机制的检出与修复能力。正式 A/B 使用相同源文、受众、体裁、篇幅上限、导出设置与评分表。

## 5. 异常处置表（识别信号 → 具体动作）

| 题面情形 | 识别信号 | 具体动作与状态 |
|---|---|---|
| 源文缺引用 | 文献 id/DOI/条目在材料中找不到，evidence 的 source 不存在 | 不联网补造；删除文献性事实或标 `[待人工确认]`，写 uncertainty；关键论断无证据则 partial |
| 数据自相矛盾 | 同 `conflict_group` 的 quote/surface 不同，evidence 报 conflict | 冻结该值，不取平均、不任选；列两个来源行号，人工确认 chosen 后才使用，否则 partial |
| 体裁与篇幅冲突 | audit 同时出现 retention 与 length，或 required_sections 与 max_chars 无法兼容 | 先压背景/重复，不压证据；仍冲突列“必须保留项 vs 上限”，交人工决定，partial |
| 材料涉密 | brief.confidential=true 或材料标密 | 设 `no_external_upload=true`、`human_review_required=true`；不调用外部服务；公开渠道还须 release_approved |
| 材料未发表 | brief.unpublished=true 或材料明确 under review/unpublished | 同上；只生成内部审阅稿，公开稿无审批即 disclosure fail，不能默认可发布 |
| 文件缺失/空文件/PDF 不可读 | 文件不存在、0 字节、提取为空或加密 | 标材料缺失及具体路径；其他材料可写则部分交付，不从标签猜内容 |
| 材料存在但证据不足 | 无样本/统计/比较基准，或只有相关证据 | 标无法判断；降调、保留未知，不补统计，不将方向写成显著 |
| 机检或导出运行失败 | 退出码 2、非法 UTF-8/JSON、磁盘错误 | 保留最后 partial 和错误文本；运行失败与材料缺失分开；修复输入后重跑，不伪造 report |
| 长文/重复运行 | 分章底账，report 带行号；脚本确定性输出 | 分章落盘、逐章审计再合并；同一输入重复机检，指标应一致 |

## 6. 资源、示例与自测

- `templates/transfer_project.json`：证据、术语、冲突裁决和逐段改动 schema；
- `templates/brief.json`、`templates/genre_skeletons.md`：受众/体裁约束和四种骨架；
- `templates/result_spec.md`：result/gain 契约；`checklists/audit_checklist.md`：人工终审；
- `examples/minimal_example.md`：完整最小调用，明确为示例；
- `docs/data_formats.md`、`docs/positioning.md`、`docs/scoring_coverage.md`：格式、创新边界、评分覆盖。

```bash
python3 bench/bench_run.py --write   # evidence/audit/result 三命令，20/20；正向零误杀、变异必命中
```

## 7. 限制与维护

机检保证“所写与底账一致、底账逐字回原文”，不替代领域专家判断原文本身是否正确；不支持 OCR 读图取数、自动文献真实性验证或任意单位换算。当前数值策略要求复制原文表面形式，换算须人工确认后作为新证据记录。复杂 Office/PDF 视觉排版不属于本 Skill 的转换重点。规则修改必须先增加正向和独立变异夹具，再改脚本，最后 20/20 全绿；版本见 `REVISION.md`。
