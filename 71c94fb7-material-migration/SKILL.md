---
name: material-migration
description: 科研资料收集与迁移：真实保留来源与归属，事务化完成字段映射、去重、SQLite/Datasette迁移、断点续跑和附件完整性校验，登录失效/下载失败/写入报错均有可机检恢复证据
---

# 科研资料收集与迁移

让一条真实资料链从来源到目标端闭合运行，中途失败后按检查点续跑，而不是重头再来。交付的不只是表格，还包括原文/响应、归属、映射、去重、事务写入、差异和恢复证据。

不适用：绕过登录/二次认证/跨域限制/付费墙，捏造全文或科学数据，以内容补全代替迁移，或在无权限时静默降级为“成功”。

## 输入、输出与事实边界

- 读取 `/input/case.json`、`/input/task.md`、`environment/resources.yaml` 和实际原始文件；只访问组织方本地服务，不访问 live external 或 Bohrium 科学空间。
- 在 `/app/work` 处理，在 `/app/output` 交付 `result.json`、实际目标库/文件、完整来源文件、日志、映射与差异报告。
- **保留原始 `output_contract` 的全部字段和 `case_id`**，本技能的字段仅增量添加。尽早就写诚实 partial；无法判断、材料缺失、运行失败分开说明。
- 按固定案例要求取得 3 个真实已发表来源，保存完整文件、来源定位、获取时间、attribution、记录数和 SHA-256；不得把 bench/本文示例当正式答案。

## 必过机检命令

```bash
python3 scripts/auto_tool.py trace /app/output/result.json
python3 scripts/auto_tool.py schema /app/output/result.json
python3 scripts/auto_tool.py recovery_check /app/output/result.json
python3 scripts/auto_tool.py migration_check /app/output/result.json
python3 scripts/auto_tool.py resume /app/output/result.json
python3 scripts/auto_tool.py manifest /app/work/source.manifest.json /app/output/<真实来源或产物> [...]
python3 scripts/auto_tool.py verify_manifest /app/work/source.manifest.json
```

全部仅 Python 标准库。`trace/schema/recovery_check/migration_check/verify_manifest` 任一失败，都不能声称 `pass`。没有失败时 `failures=[]` 可通过 `recovery_check`，但实际 failed/blocked 步骤必须有恢复事件。

## 工作流与完成标准

### 0. 原契约、版本和真实来源快照

从 case 读取原字段写入 `input_contract.required_fields/preserved_fields`，若指定来源数则填 `expected_source_count`。`schema` 会检查原字段仍在 result 顶层、版本非空、collection 实际来源数符合 case。

`collection` 每个来源至少填：

```json
{"source_id":"S1","locator":"实际本地URL或文件定位","retrieved_at":"实际时间",
 "retained_file":"完整原文件路径","sha256":"manifest计算的摘要",
 "attribution":"作者/标题/出版者/年份/DOI或许可等实际归属","record_count":1}
```

分页源保存每页 URL/响应，滚动源保存最终状态；登录后的 HTML 不能当论文全文。案例要求 Datasette 时，对实际 HTTP 服务完成分页、过滤、CSV、HTML，并保留请求参数、状态码、响应和行数。

### 1. DAG 与状态：可复跑而非口头描述

`workflow` 每步写 `id/step/depends_on/input/output/state`，状态为 `pending/done/failed/blocked/skipped`。`trace` 硬检查依赖存在且无环、输入输出、状态、`state.completed_steps` 与 done 集一致、失败有 resume_point、跨站权限及字段映射。

```bash
python3 scripts/auto_tool.py resume /app/output/result.json
```

只有依赖全部 done 的未完成步骤进入 `runnable_now`；`already_done_not_replayed` 防重放，`needs_intervention_not_replayed` 保留 blocked/skipped。**skipped 不算依赖完成**，blocked 不自动执行。

### 2. 字段映射：不静默错列、截断、填假值

顶层 `field_mapping` 每项写 `source_field/target_field/transform/on_missing`，覆盖命名、类型、编码、日期、作者、单位转换；`data_passing` 也保留对应映射与权限范围。目标字段重复会报“静默覆盖”。

不可映射项进入 `unmapped={source_field,reason,action}`，保留在 raw 文件；需要保留原值还是批准留空必须说清。缺字段不填假值，`field_missing` 恢复事件要求 `substitute_value_used=false`。

### 3. 去重：决策留证，疑似不等于精确

`deduplication.decisions` 每项至少有两条 `record_refs`，以及 `decision/reason/evidence/removed_count`：

- `exact_duplicate`：标识符等精确判据成立，可删除冗余目标记录。
- `merged_duplicate`：别名/身份经真实来源确认后合并，保留各成员来源和合并证据。
- `suspected_duplicate`、`distinct`、`same_name_different`：必须 `removed_count=0`，不得自动误合并。

`integrity.exact_duplicates/merged_duplicates` 必须分别等于两类决策的 removed_count 之和。

### 4. 事务迁移：初始目标、批次、检查点、回滚都可定位

若案例给定初始 SQLite，必须先备份原始库，在事务中执行 collection/migration、identity/alias、restoration/recovery/conflict 操作，不能交付一个脱离初始库的新表就声称完成。`migration` 写实际目标、transaction_id、checkpoint、rollback_ref、`transactional=true`。

`migration.write_log` 每批记录 `batch_id/idempotency_key/attempted_count/accepted_count/rejected_count`。同一逻辑失败的多 attempt 合并为一个 failures 事件，重试沿用原幂等键；不同逻辑失败不得复用键。重复运行不得产生第二条目标记录或二次推送。

### 5. 三类重点异常及其他失败处置

每个 `failures` 事件统一保留 `step/category/error/detection/action/recovery/disposition/outcome/occurred_at/resume_point/idempotency_key`。恢复后原事件仍保留并置 `outcome=recovered`。

| 失败 | 必备专项字段与处置 |
|-|-|
| **登录态失效** `login_state_expired` / 二次认证 `mfa_required` | `site/auth_state/human_required=true/credential_material_logged=false`；停止并 `manual` 请求认证，从检查点续跑，禁止绕过 |
| **下载失败** `download_failed` | `source_locator/artifact/content_check{expected,observed}/partial_file_retained`；保留 .part，分段或有界重试；恢复后 `verification` 校验哈希或大小+Content-Type |
| **写入报错** `write_failed` | `target/batch_id/transaction_id/transactional` 和 attempted/accepted/rejected；计数必须闭合，失败行隔离后续写，回滚须有 `rollback_ref` |
| 字段缺失 `field_missing` | 记 source_field、record_locator，标 unmapped，不伪造默认值 |
| 权限不足 `permission_denied` / 跨域 `cross_origin` | 写 required_permission/边界，`manual` 等授权，不越权重试 |
| 元素缺失 `element_missing` | 保存选择器、URL/页面版本，备用定位验证后 fallback，否则人工 |
| 超时 `timeout` / 限流 `rate_limited` | 有界指数退避并记录尝试；超限 failed + resume_point，不无限重试 |
| 同步冲突 `sync_conflict` | left/right version_ref 双留、`both_versions_retained=true`，按约定合并或人工，不覆盖 |

`recovery_check` 会逐类验证上述硬约束，同时检查所有 write_log 计数。坏 JSON、缺参数、缺文件均输出结构化错误并非零退出。

### 6. 完整性校验：记录数、去重数和附件清单都要闭合

`integrity` 至少填：

```json
{"source_count":10,"target_count":8,"exact_duplicates":1,"merged_duplicates":1,
 "skipped_count":0,"added_count":0,"expected_differences":[],"unexpected_differences":[],
 "source_attachments":3,"target_attachments":2,
 "expected_missing_attachments":[],"unexpected_missing_attachments":[]}
```

其中 `added_count` 是目标新增但并非来自这些源记录的条数。机检恒等式：

```text
source_count = target_count + exact_duplicates + merged_duplicates + skipped_count - added_count
```

collection 各 record_count 之和还须等于 source_count。附件差值必须逐项列入 expected/unexpected 清单；存在非预期字段或附件差异时不能 `status=pass`。计数相等但关键字段/标识符不一致仍是缺陷，写入差异清单，不能用恒等式掩盖。

### 7. 文件证据与公平增益

`manifest` 读取真实字节生成 size/SHA-256；`verify_manifest` 重读文件复核，改动或缺失必失败。`artifacts` 和 collection 的哈希必须来自实际文件，不能填写占位符。

`gain` 仅填平台或公平同输入、同权限、同初始目标对照给出的成功率、人工修改量、重复迁移和耗时；未提供时为 null。不得自行编造基础 Agent 分数或提升比例。

## result.json 增量契约（结构示例，非正式结果）

```json
{
  "case_id":"实际case_id", "status":"pass|issues|partial|failed",
  "schema_version":"2.0", "skill_version":"2.0.0", "run_version":"实际运行ID",
  "input_contract":{"case_path":"/input/case.json","task_path":"/input/task.md",
    "required_fields":["case_id","...原字段"],"preserved_fields":["case_id","...原字段"],"expected_source_count":3},
  "workflow":[{"id":"W1","step":"采集","depends_on":[],"input":"case sources","output":"raw/*","state":"done"}],
  "state":{"completed_steps":["W1"],"failed_step":"","resume_point":""},
  "collection":[], "field_mapping":[], "unmapped":[],
  "data_passing":[{"from":"W1","to":"W2","field_mapping":{"title":"name"},"permission_scope":"green","permission_ref":"P1"}],
  "permission_records":[{"id":"P1","site":"本地目标","role":"writer","status":"active"}],
  "deduplication":{"decisions":[]},
  "migration":{"target":"实际SQLite路径","transaction_id":"实际ID","transactional":true,
    "checkpoint":"实际检查点","rollback_ref":"实际备份","write_log":[]},
  "integrity":{}, "failures":[], "sync_conflicts":[], "artifacts":[],
  "run_log":[{"step":"W1","start":"实际时间","end":"实际时间","result":"ok"}],
  "gain":{"baseline_success_rate":null,"skill_success_rate":null,"manual_steps_saved":null},
  "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]
}
```

空 collection/mapping/integrity 只用于说明字段位置，正式交付必须填实际值并通过全部命令。

## 最小调用示例（合成展示，不是测评结果）

```bash
python3 scripts/auto_tool.py recovery_check /app/output/result.json
# 登录、下载和写入三个恢复事件均合规时示意：{"ok":true,"checked_failures":3,...}
python3 scripts/auto_tool.py resume /app/output/result.json
# W1/W2 done、W3 failed 且 resume_point=W3 时示意：runnable_now=["W3"]，不会重采 W1/W2
```

## 自测

```bash
python3 bench/bench_run.py   # 合成正向零误杀 + 变异必命中
```

自测只验证工具，不代替固定案例的真实运行。任何未能完成的操作都保留 partial 和不确定性，不把权限、下载或写入问题隐藏在最终表格之外。
