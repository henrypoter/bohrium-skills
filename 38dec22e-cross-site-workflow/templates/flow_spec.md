# 跨站流程规格（flow_spec.md，模板非正式结果）

## 步骤表
| id | 步骤 | 依赖 | 输入 | 输出 | 状态 | 幂等键 |
|-|-|-|-|-|-|-|
| W1 | 检索下载 | — | query | files[] | done | W1-<run>-01 |
| W2 | 字段抽取 | W1 | files[] | rows[] | done | W2-<run>-01 |
| W3 | 事务写入目标 | W2 | rows[] | ids[] | pending | W3-<run>-01 |

每次状态变化另写 `state_history={step,from,to,at}`。任何 done/failed/blocked 步骤都需对应操作记录；failed/blocked 还需恢复分类和顶层 resume_point。

## 操作证据
| step | kind | action | URL/软件与版本 | 页面版本/窗口文档/HTTP状态 | evidence |
|-|-|-|-|-|-|
| W1 | browser/api/software | 实际动作 | 实际定位 | 实际版本或状态 | 实际日志/响应/截图路径 |

Datasette 按任务保留分页、过滤、CSV、HTML 请求与响应；SQLite 保留原库备份、transaction_id、checkpoint、rollback_ref 和目标查询。

## 跨站交接
| 源 | 源字段 | 目标 | 目标字段 | 转换/单位/编码 | 权限与permission_ref | 源条数 | 目标条数 | 源/目标快照 |
|-|-|-|-|-|-|-|-|-|
| 文献库 | title | 笔记 | name | 去标签/none/utf-8 | green/P1 | 10 | 10 | 实际文件哈希 |

- `green` 直传；`yellow` 必须写 deidentification；`red` 仅 hash_or_id_only/blocked。
- 不等计数必须有逐项 expected_differences，否则 flow_check 失败。

## 失败与冲突
- 每事件记录 category/detection/action/disposition/outcome/resume_point/idempotency_key。
- 登录、二次认证、跨域、权限拒绝：停止并 manual，不绕过。
- 下载：保留 .part，恢复后校验 Content-Type/大小/SHA-256。
- 写入：attempted=accepted+rejected，事务续写或 rollback_ref。
- 冲突：left/right 均保留 version、value_ref、retained_path；pending 不得 pass。

## 交付核验
- [ ] `flow_check`、`schema`、`audit` 全通过。
- [ ] `resume` 不重复 done，不自动执行 blocked/skipped。
- [ ] `artifacts` 来自 manifest，`verify_manifest` 重算通过。
- [ ] 原 output_contract 字段、case_id、来源数、版本字段齐全；无对照的 gain 为 null。
