# 资料采集迁移流程规格（模板，非正式结果）

## 1. 状态与步骤

`pending → done`；失败进入 `failed` 并保留 resume_point；权限/认证问题进入 `blocked`；条件不满足为 `skipped` 且写原因。blocked/skipped 均不计完成，也不被 resume 自动重放；只有 done 能满足下游依赖。

| id | 步骤 | 依赖 | 输入 | 输出 | 幂等键 |
|-|-|-|-|-|-|
| W1 | 分页采集并保留完整来源 | — | case sources | raw/* + collection | W1-<run>-01 |
| W2 | 映射与去重 | W1 | raw/* | mapped.jsonl + decisions | W2-<run>-01 |
| W3 | 事务写入初始SQLite | W2 | mapped.jsonl | record_ids[] + write_log | W3-<run>-01 |

## 2. 来源、映射与权限

collection 每源填 source_id/locator/retrieved_at/retained_file/sha256/attribution/record_count。按 case 要求保留 3 个真实来源；Datasette 的分页、过滤、CSV、HTML 请求和响应均留存。

| 源字段 | 目标字段 | transform（类型/编码/单位/日期） | on_missing |
|-|-|-|-|
| title | name | strip_html / utf-8 | mark_unmapped |
| doi | identifier | normalize_doi | allow_null或按case要求 |

unmapped 每项写 reason/action。green 可传；yellow 先脱敏；red 禁止外传。账号只写安全别名，不写密码/token/cookie。

## 3. 去重与完整性

- 决策：exact_duplicate / merged_duplicate / suspected_duplicate / distinct / same_name_different。
- 每项至少两个 record_refs，附 reason/evidence/removed_count；疑似和同名不同文献不得删除。
- `source = target + exact + merged + skipped - added`。
- collection 的 record_count 总和等于 source_count；附件差值逐项列 expected/unexpected。
- 非预期字段或附件差异存在时不得 pass。

## 4. 失败恢复专项表

| category | 检测与保留 | 恢复 |
|-|-|-|
| login_state_expired/mfa_required | site/auth_state，不记录凭据 | 停止转人工；认证后 checkpoint 续跑 |
| download_failed | expected/observed Content-Type等，.part保留状态 | 有界续传，恢复后哈希或大小+类型验证 |
| write_failed | transaction/batch，attempted=accepted+rejected | 失败行隔离，幂等续写或 rollback_ref |
| field_missing | source_field/record_locator | unmapped，不填假值 |
| permission_denied/cross_origin | required_permission/边界 | 等授权，不越权 |
| sync_conflict | 左右version_ref均保留 | 人工或按约定合并，不覆盖 |

每事件统一写 step/error/detection/action/recovery/disposition/outcome/occurred_at/resume_point/idempotency_key；恢复后原事件保留并标 recovered。

## 5. 交付前自检

- [ ] `trace/schema/recovery_check/migration_check` 全通过。
- [ ] migration 有初始库备份、transaction_id、transactional=true、checkpoint、rollback_ref 和批次计数。
- [ ] `resume` 不重跑 done，不把 skipped 当完成，不自动执行 blocked。
- [ ] `manifest` 来自真实文件，`verify_manifest` 重算通过。
- [ ] 原 output_contract、case_id、来源数、schema/skill/run 版本齐全；无真实对照的 gain 为 null。
