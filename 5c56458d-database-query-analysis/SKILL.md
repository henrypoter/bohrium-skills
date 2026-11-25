---
name: database-query-analysis
description: 科研数据库查询与分析：查询在授权数据快照上直接执行、结果与金标准或独立复算对上、字段字典与关联路径可复核、一对多膨胀受控
---

# 科研数据库查询与分析

把研究问题转成**在授权数据快照上可执行的查询**，结果与金标准或独立复算对上，字段含义与关联路径写清，让人能按记录复跑核对。

**不适用**：生产数据库运维、未授权数据的获取、替代统计方法学。只读查询不得越权写入，模型生成的 SQL 是**待执行的候选**，须在授权快照上验证后才算结果。

## 判对三件事（本题评分核心，不看写了多少行 SQL）

1. **查询能在授权的数据快照上直接执行**——`snapshot` 版本 + `connection` 权限范围写清。
2. **结果与金标准或独立复算对上**——每条查询给 `golden` 或 `recheck`。
3. **字段含义与关联路径可复核**——`field_dict` 每条有含义，`joins` 每条有连接键与膨胀控制。

三件事各有一条机检闸：
```bash
python3 scripts/query_tool.py query_check result.json
```

## 调用
- 输入：`/input/case.json`、`/input/task.md`、数据库连接信息 + 数据快照
- 输出：`/app/output/result.json` + 结果集
- 工具：`scripts/query_tool.py`（`query_check` / `schema`）

## 工作流（五个方向逐一过）

### 0. 锁定快照与权限
记录 `query_version` + 每条查询的 `snapshot`（数据快照版本）+ `connection.permission`（读/写/只读范围）。**快照版本不写，结果无法复算**。

### 1. 数据库连接（方向1）
写清连接参数、权限范围、库表发现与快照版本。哪些库可读写、哪些只能只读，必须显式区分。

### 2. 查询语句（方向2）
由问题生成可执行 SQL，处理时间范围、筛选条件、排序与分页。报错后能定位与修复——把报错信息与修复过程记进 `change_log`。SQL 须在快照上**实际执行**，不是手写结果。

### 3. 结果抽取（方向3）
结果集稳定导出为可核对结构，处理字段类型、单位、编码、缺失值、重复记录。每条查询给 `result` + `golden`（金标准）或 `recheck`（独立复算口径），对不上给容差并归因。

### 4. 字段解释（方向4）
依据数据字典给 `field_dict`：字段含义、取值范围、统计口径，识别易混字段（如样本状态 vs 实验状态）并说明取舍。

### 5. 跨表分析（方向5）
`joins` 每条写 `left / right / on`（连接键）+ `one_to_many`（一对多膨胀控制说明）。选错连接键或膨胀失控都会让结论失真。

### 6. 增益对照
同快照、同权限，基础 Agent vs 本 Skill 各跑一次，报：查询可执行率、结果与金标准一致率、人工改 SQL 次数。

### 7. 异常处置
| 异常 | 动作 |
|-|-|
| 权限不足 | 标 `blocked`，写清缺什么权限，不算完成 |
| 快照版本不明 | 标 `unknown`，结论降级并注明"快照版本不明，结果不可复算" |
| 查询报错 | 记录报错 + 定位 + 修复，重跑验证 |
| 字段含义歧义 | 并列两种读法，标 `uncertainty`，不无依据取舍 |
| 结果对不上 | 给容差并归因（字段/口径/过滤），不硬说一致 |
| 一对多膨胀 | 声明膨胀倍数与去重口径，未控制不报结论 |

### 8. 诚实输出
```bash
python3 scripts/query_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{
  "case_id": "", "status": "pass|issues|partial|failed", "query_version": "v1",
  "queries": [{"id": "Q1", "snapshot": "", "connection": {"permission": "read-only"}, "sql": "",
               "result": [], "golden": null, "recheck": ""}],
  "field_dict": [{"field": "", "meaning": "", "range": "", "note": ""}],
  "joins": [{"left": "", "right": "", "on": "", "one_to_many": false}],
  "results": [], "gain": {"baseline_exec_rate": null, "skill_exec_rate": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
查询在授权快照上执行、结果与金标准/复算对上、字段与关联路径可复核、膨胀受控。不越权、不编结果、不把"没对上"说成"一致"。
