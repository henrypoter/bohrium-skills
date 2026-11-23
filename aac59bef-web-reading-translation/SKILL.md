---
name: web-reading-translation
description: 网页文献阅读与翻译：步骤依赖成 DAG 且无环、状态随手记录、断点续跑、跨站权限与幂等重试
---

# 网页文献阅读与翻译

让一条真实任务**从头跑到尾，中途失败接着跑**，并把每一步的状态与数据交接记录下来，他人可按文档复跑。

不适用：绕过站点风控、破解付费墙、替代人工判断的最终确认。账号权限不足时明确降级。

## 调用

- 输入：`/input/case.json`、`/input/task.md`、站点/软件清单与账号权限
- 输出：`/app/output/result.json` + 中间产物 + 运行日志
- 工具：`scripts/auto_tool.py`（`trace` / `resume` / `schema`）
- 模板：`templates/flow_spec.md`（状态机 + 站点选择器与字段映射 + 权限分级）

## 工作流

### 0. 拆步骤，先画依赖
每个步骤写 `id / step / depends_on / input / output`。依赖必须构成 **DAG（无环）**：出现环说明任务拆错了。

### 1. 状态机：每步只有四种状态
`pending / done / failed / skipped`。每步执行后立刻写状态，**不要任务结束才补记**。

### 2. 校验编排
```bash
python3 scripts/auto_tool.py trace result.json
```
它会抓：依赖指向不存在的步骤、依赖成环、步骤缺 input/output、有 `failed_step` 却缺 `resume_point`、幂等键重复、跨站数据未声明 `permission_scope`。

### 3. 断点续跑（不是重头再来）
```bash
python3 scripts/auto_tool.py resume result.json
```
输出 `runnable_now`（依赖已满足、可立即执行的步骤）与 `waiting`（还缺哪些上游）。按它续跑，**已完成步骤不重复执行**。

### 4. 跨站数据交接
每条 `data_passing` 写：`from / to / field_mapping（源字段→目标字段）/ permission_scope（green/yellow/red）`。转换规则（单位、编码、日期格式）写进映射表，传完做一次完整性校验（条数、关键字段非空）。

### 5. 失败恢复与幂等
每个失败记录 `step / error / recovery / retry / idempotency_key`。重试必须幂等：同一 `idempotency_key` 重复执行不得产生第二条记录或第二次推送。

### 6. 增益对照
同输入、同账号权限，基础 Agent vs 本 Skill 各跑一次，报：任务成功率、人工搬运/重复点击次数、整链重跑次数。

### 7. 异常处置
| 异常 | 动作 |
|-|-|
| 登录失效 / 二次认证 | 停止并请求人工完成认证，记录中断点；**不尝试绕过** |
| 页面元素缺失（改版） | 记 `failed` + 选择器失效，回退到备用选择器或人工，不静默跳过该步 |
| 接口超时 / 限流 | 指数退避重试，超过次数标 `failed` 并保留 `resume_point` |
| 权限拒绝 | 该步标 `blocked` 并写清缺什么权限，不算完成 |
| 同步冲突（两边都改过） | 保留两份、标 `conflict`、交人工裁决，不自动覆盖 |
| 字段缺失/类型不符 | 该字段记 `unmapped`，产出里显式标注，不填假值 |

### 8. 诚实输出
```bash
python3 scripts/auto_tool.py schema /app/output/result.json
```

## result.json 契约

```json
{
  "case_id": "", "status": "pass|issues|partial|failed",
  "workflow": [{"id": "W1", "step": "", "depends_on": [], "input": "", "output": "", "state": "done"}],
  "state": {"completed_steps": [], "failed_step": "", "resume_point": ""},
  "data_passing": [{"from": "W2", "to": "W3", "field_mapping": {"title": "name"}, "permission_scope": "green"}],
  "failures": [{"step": "W3", "error": "", "recovery": "", "retry": 0, "idempotency_key": ""}],
  "run_log": [{"step": "W1", "start": "", "end": "", "result": "ok", "note": ""}],
  "gain": {"baseline_success_rate": null, "skill_success_rate": null, "manual_steps_saved": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
状态随手记、失败可续跑、跨站数据有权限范围、重试幂等。做不到的步骤标 blocked，不假装完成。

## 本课题聚焦
本题聚焦**网页论文抓取与分语对照**：抓下来的必须是论文正文而非导航广告，正文/摘要/图表分离；译文逐段对得上原文并保留原文，术语全文一致并留术语表；读者能凭交付物回到原始页面核对每条内容。
