---
name: cross-site-workflow
description: 跨网站科研工作流自动化：把多个站点的任务排成无环 DAG，每步记录输入输出与状态，字段映射与权限分级显式，迁移前后条数闭合，失败断点续跑且幂等重试
---

# 跨网站科研工作流自动化

## 用途与边界
把「检索→采集→清洗→写入」这类跨站任务编排成一条**能断点续跑、能复核**的工作流：依赖无环、状态随手记、字段对齐、权限分级、迁移完整、重试幂等。不适用：绕过站点风控、破解付费墙、替代人工最终确认。

## 调用
- 输入：`/input/case.json` + 站点/账号权限清单 + `task.md`
- 输出：`/app/output/result.json` + 中间产物 + 运行日志
- 工具：`scripts/crosssite_tool.py`（`flow_check` / `schema`）
- 模板：`templates/flow_spec.md`

## 工作流

### 0. 拆步骤画 DAG
每步 `id / step / depends_on / input / output`。依赖无环，出现环说明拆错。

### 1. 状态机随手记
`pending / done / failed / blocked / skipped` 五态，每步执行后立刻写状态，不补记。

### 2. 编排机检
```bash
python3 scripts/crosssite_tool.py flow_check result.json
```
抓：依赖不存在、依赖成环、状态非法、失败无续跑点、幂等键重复。

### 3. 跨站交接：字段映射 + 权限分级 + 条数闭合
每条 `data_passing` 写 `field_mapping`（源字段→目标字段+转换规则）、`permission_scope`（green/yellow/red）、`source_count` 与 `target_count`。
- `green` 可直接传；`yellow` 脱敏后传；`red` 禁止外传（用哈希/ID 代替）。
- **迁移前后条数必须闭合**：`source_count == target_count`，不等即丢数据/重复。
```bash
python3 scripts/crosssite_tool.py flow_check result.json   # 同样抓迁移条数不符
```

### 4. 断点续跑 + 幂等重试
失败步骤标 `failed` 并写 `resume_point`；重试用同一 `idempotency_key` 不产生第二条记录或第二次推送。

### 5. 增益对照
同输入、同账号权限，基础 Agent vs 本 Skill 各跑一次，报：任务成功率、人工搬运次数、整链重跑次数。

### 6. 异常处置
| 异常 | 动作 |
|-|-|
| 登录失效/二次认证 | 停止并请求人工认证，记中断点，不绕过 |
| 页面改版/元素缺失 | 标 failed + 回退选择器，不静默跳过 |
| 超时/限流 | 指数退避重试，超限标 failed 留 resume_point |
| 权限拒绝 | 标 blocked，写清缺什么权限，不算完成 |
| 同步冲突 | 保留两份标 conflict 交人工，不自动覆盖 |
| 迁移条数不符 | 定位缺失/重复条目，回补后重跑校验 |

### 7. 诚实输出
```bash
python3 scripts/crosssite_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{"case_id":"","status":"pass|issues|partial|failed","run_version":"v1",
 "steps":[{"id":"W1","step":"","depends_on":[],"input":"","output":"","state":"done"}],
 "data_passing":[{"from":"W1","to":"W2","field_mapping":{"title":"name"},
                  "permission_scope":"green","source_count":10,"target_count":10}],
 "resume_point":"","idempotency_keys":[],
 "run_log":[{"step":"W1","start":"","end":"","result":"ok"}],
 "gain":{"baseline_success_rate":null,"skill_success_rate":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 底线
依赖无环、状态随手记、字段映射与权限分级显式、迁移条数闭合、失败可续跑、重试幂等。做不到的步骤标 blocked，不假装完成。
