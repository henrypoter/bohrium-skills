---
name: cross-site-workflow
description: 跨网站科研工作流自动化：真实执行 DAG 跨站任务，保留浏览器/软件定位、状态快照、字段与权限边界、事务检查点、冲突双版本和 SHA-256 证据，失败后续跑而非整链重跑
---

# 跨网站科研工作流自动化

## 用途与边界

把固定案例中的「采集 → 转换 → SQLite/Datasette/软件目标 → 回填」实际跑到目标状态。判对不看脚本长度，只看：**端到端完成且能从检查点续跑；输入/输出/状态可由他人复跑；数据与权限始终落在约定边界内**。不绕过登录、二次认证、跨域限制或付费墙，不伪造页面/软件状态，不替代冲突的人工裁决。

只使用 `case.json`、`task.md` 和组织方本地服务。不得把示例或 bench 当正式案例答案；不得擅自访问外站或 Bohrium 科学空间。

## 调用与产物

- 输入：`/input/case.json`、`/input/task.md`、`environment/resources.yaml` 及案例给定账号/权限。
- 工作区：`/app/work`；最终交付：`/app/output`。
- 工具：`scripts/crosssite_tool.py`，仅 Python 标准库。
- 先读原始 `output_contract`，**保留全部原字段及 `case_id`，以下字段只能增量添加，不能替换原契约**。
- 尽早就写诚实 partial，再逐步改善；Office/图表产物按要求附真实 PDF/PNG 预览。

## 必过判对闸

在 `/app/submission`（安装后为技能所在目录）执行，路径按实际调整：

```bash
python3 scripts/crosssite_tool.py flow_check /app/output/result.json
python3 scripts/crosssite_tool.py schema /app/output/result.json
python3 scripts/crosssite_tool.py audit /app/output/result.json
python3 scripts/crosssite_tool.py resume /app/output/result.json
python3 scripts/crosssite_tool.py manifest /app/work/artifacts.manifest.json /app/output/<真实产物> [...]
python3 scripts/crosssite_tool.py verify_manifest /app/work/artifacts.manifest.json
```

任一 `flow_check/schema/audit/verify_manifest` 非零，不得声称 `pass`。`resume` 是续跑计划，不改变状态；`done` 和需人工的 `blocked/skipped` 不会被自动重放。

## 实际工作流

### 0. 读取事实、契约和权限

读取实际案例与原文件，记录来源版本/定位。按案例要求取得 **3 个真实已发表来源**，保留全文或完整来源文件、作者/标题/年/DOI或URL、授权/归属、获取时间和 SHA-256；缺材料、权限不足、运行失败分别标记，不能互相冒充。只使用组织方本地 URL。

将原契约写入 `input_contract.required_fields/preserved_fields`；`expected_source_count` 若案例有规定则照实填。账号只写 `account_ref`（安全别名），不得写密码、token、cookie。

### 1. DAG 与任务状态：每步有输入、输出和完成标准

每步写 `id / step / depends_on / input / output / state`，状态为 `pending/done/failed/blocked/skipped`。每次转换立即追加 `state_history={step,from,to,at}` 和 `run_log`，不是在末尾补记。`done` 必须由真实目标状态或产物证明；`blocked/skipped` 不算完成。

失败时设置顶层 `resume_point`，重试同一逻辑写操作沿用同一幂等键；不同逻辑操作不得碰键。`resume` 只把依赖全部为 `done` 的未完成步骤列入 `runnable_now`，避免整链重跑。

### 2. 浏览器、API、软件操作：保存可定位证据

每次已执行步骤至少一条 `operations` 记录：

- 浏览器：`kind=browser`，定位含最终 `url`、`page_version`（DOM/响应哈希或站点版本）、`selector`，另附 `evidence`。
- API：`kind=api`，定位含 URL 和实际 `http_status`，保存分页、过滤参数及响应文件。
- 软件：`kind=software`，定位含软件名、版本、窗口或文档标识；不能用自然语言假装已点击。

若案例指定 Datasette，必须对实际目标 HTTP 服务完成任务要求的分页、过滤、CSV 和 HTML 操作，保留 URL、状态码、请求参数、原响应与行数；仅生成一个相似 CSV 不算完成。若指定初始 SQLite，先备份原库，事务内执行采集/迁移、身份与别名、恢复、冲突操作，记录事务 ID、检查点、回滚引用和目标查询结果。

### 3. 跨站数据传递：字段、权限、计数三重闭合

每条 `data_passing` 写源/目标快照、`source_count/target_count`、`permission_ref/permission_scope`。`field_mapping` 每字段必须为：

```json
{"源字段":{"target":"目标字段","transform":"去标签/DOI规范化/单位或日期转换","encoding":"utf-8","unit":"none"}}
```

缺失、不可映射、预期差异逐项列出，不得通过丢掉字段让计数假闭合。权限 `green` 可直传，`yellow` 必须有 `deidentification`，`red` 只能 `hash_or_id_only` 或 `blocked`。每条权限记录写站点、账号别名、角色、scopes 和状态；实际传输时权限必须为 `active`。

### 4. 失败恢复：分类、处置、结果、续跑点都可查

每个失败写 `step/category/error/detection/action/disposition/outcome/resume_point/idempotency_key`，并关联实际日志。`disposition` 仅用 `retry/fallback/skip_declared/manual/rollback`。

| 异常（category） | 必须动作与证据 |
|-|-|
| 登录失效 `login_state_expired` / 二次认证 `mfa_required` | 立即停止该站写入，`manual` 转人工，保留检查点；不记录凭据，不绕过 |
| 跨域 `cross_origin` / 权限拒绝 `permission_denied` | 不试探越权；记录边界/缺的角色，`manual` 等授权或明确降级 |
| 页面改版/元素缺失 `element_missing` | 保存 URL、页面版本和失效选择器；仅在备用定位验证后 `fallback`，否则人工 |
| 超时 `timeout` / 限流 `rate_limited` | 有界指数退避，记录次/间隔/最终响应；超限保持 failed 和检查点 |
| 下载失败 `download_failed` | 保留 `.part`，校验 Content-Type/大小/哈希，不能将登录 HTML 当全文 |
| 写入报错 `write_failed` | 记录事务、批次、attempted/accepted/rejected；隔离失败行后幂等续写或回滚 |
| 同步冲突 `sync_conflict` | 双方版本和值引用都保留，按约定合并或 `manual`，不静默覆盖 |

恢复成功也要保留原失败事件和 `outcome=recovered`；不能只写“已重试”。

### 5. 冲突与最终一致性

`sync_conflicts` 每项包含 `record_id`、左右两侧的 `version/value_ref/retained_path`、`resolution` 和证据。未裁决冲突必须保持 `issues/partial`，不得 `pass`。迁移计数不相等时，只能凭 `expected_differences` 解释，否则 `flow_check` 失败。

### 6. 产物哈希与增益证据

用 `manifest` 对实际文件计算大小和 SHA-256，将路径、摘要、步骤、类型写入 `artifacts`；`verify_manifest` 重新读取字节核验。只写伪造的 64 位字符串不能通过 `audit`，真实字节变化不能通过 `verify_manifest`。

`gain` 只填平台或公平同输入/同权限对照提供的真实成功率、整链重跑和人工搬运数据；没有对照就为 `null` 并说明，禁止编造提升比例。

## result.json 增量契约（结构示例，非正式结果）

```json
{
  "case_id":"实际case_id", "status":"pass|issues|partial|failed",
  "schema_version":"2.0", "skill_version":"2.0.0", "run_version":"实际运行标识",
  "input_contract":{"case_path":"/input/case.json", "task_path":"/input/task.md",
    "required_fields":["case_id","...原字段"], "preserved_fields":["case_id","...原字段"], "expected_source_count":3},
  "steps":[{"id":"W1","step":"采集","depends_on":[],"input":"query","output":"raw/source.json","state":"done"}],
  "state_history":[{"step":"W1","from":"pending","to":"done","at":"实际时间"}],
  "operations":[{"step":"W1","kind":"browser","action":"extract","evidence":"logs/W1.jsonl",
    "locator":{"url":"实际本地URL","page_version":"响应哈希","selector":"实际选择器"}}],
  "data_passing":[{"from":"W1","to":"W2","field_mapping":{},"permission_ref":"P1",
    "permission_scope":"green","source_count":0,"target_count":0,
    "source_snapshot":"实际文件#sha256", "target_snapshot":"实际文件#sha256"}],
  "permissions":[{"id":"P1","site":"本地站点","account_ref":"安全别名","role":"实际角色","scopes":[],"status":"active"}],
  "failures":[], "sync_conflicts":[],
  "artifacts":[{"path":"实际路径","sha256":"manifest所得摘要","kind":"output","step":"W1"}],
  "resume_point":"", "idempotency_keys":[], "run_log":[{"step":"W1","start":"实际时间","end":"实际时间","result":"ok"}],
  "gain":{"baseline_success_rate":null,"skill_success_rate":null},
  "unchecked":[], "sources":[], "uncertainty":[], "change_log":[]
}
```

上面 `field_mapping` 空对象仅为展示字段位置，实际运行时若存在 `data_passing` 必须填具体映射。`sources` 填实际来源定位与版本，`unchecked` 区分材料缺失/无法判断/运行失败。

## 最小调用示例（合成展示，不是测评结果）

对已经按上述契约生成的 `/app/output/result.json`：

```bash
python3 scripts/crosssite_tool.py audit /app/output/result.json
# 合规时示意输出：{"ok": true, "coverage": {"operations": 2, "state_events": 2, ...}}
python3 scripts/crosssite_tool.py resume /app/output/result.json
# W1/W2 done、W3 pending 且依赖 W2 时示意：runnable_now=["W3"]，不会重跑 W1/W2
```

## 自测与底线

```bash
python3 bench/bench_run.py   # 合成正向零误杀 + 变异必命中
```

没有真实操作、来源、状态转换、权限、传递、恢复和冲突记录之一，就明确标相应缺口；没有失败/冲突时对应数组可为空，但不能捏造事件。`status=pass` 必须所有步骤完成、证据齐全且无未裁决冲突/非预期差异。
