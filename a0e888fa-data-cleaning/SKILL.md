---
name: data-cleaning
description: 科研数据清洗与处理：先画像后计算，聚合值用原始数据独立复算，记录数据快照与字段字典
---

# 科研数据清洗与处理

从原始数据出发回答分析问题：**先画像、再计算、必复算**。每个结论都能回到原始行与数据快照。

不适用：替代领域专家的因果推断、建模创新、论文写作。数据权限不足时如实降级，不臆造数值。

## 调用

- 输入：`/input/case.json`、`/input/task.md`、数据文件（CSV/Excel）与数据字典
- 输出：`/app/output/result.json` + 结果表
- 工具：`scripts/data_tool.py`（`profile` / `recheck` / `schema`）
- 模板：`templates/data_dictionary.md`（字段字典 + 查询模式 + 复算清单）

## 工作流

### 0. 记录血缘（不记就没法复算）
写 `lineage`：数据快照版本、涉及的表/文件、筛选条件、连接键、执行时间。**没有快照版本的数值不可复核**。

### 1. 先做数据画像，再动手算
```bash
python3 scripts/data_tool.py profile data.csv
```
逐列看输出：`missing` / `duplicate_rows` / `outliers_iqr` / `scale_warning`（同列量级跨 ≥3 个数量级 → 疑单位不一致）/ `dirty_numeric_count`（该是数值却有非数值，如 `N/A`）。
**画像结果要写进 `unchecked` 或 `uncertainty`**：例如"该列 12% 缺失，均值按可得值计算"。

### 2. 字段语义接地
按 `templates/data_dictionary.md` 把每个用到的字段写成：字段名 / 含义 / 单位 / 编码含义（如 1=男 2=女）/ 缺失表示。**编码型字段当数值算是最常见的错误**。

### 3. 查询与聚合
- 连接必须写连接键与基数（1:1 / 1:N）；**漏写连接条件导致行数膨胀**是第二大坑，聚合前先看 `count(*)` 是否符合预期。
- 聚合粒度必须回答"每个数字对应哪一行/哪个人/哪个时间点"。

### 4. 结论必须可独立复算
把每个上报数值写进 `aggregates`，然后：
```bash
python3 scripts/data_tool.py recheck result.json --csv data.csv
```
脚本会从原始数据**重算** sum/count/mean/min/max 并与上报值比对（相对容差 1e-3）。不一致必须查明是口径差异还是算错，并在 `change_log` 记录。

### 5. 增益对照
同数据快照、同账号权限、同预算，基础 Agent vs 本 Skill 各跑一次，报：查询正确率、返工轮次、人工核对条数。

### 6. 异常处置
| 异常 | 动作 |
|-|-|
| 空结果 | 分清"确实没有"与"筛选写错"：放宽一个条件重跑对比，如实写哪一种 |
| 连接失败/权限不足 | 记 `unchecked` 并说明缺哪张表/哪列，不猜测补数 |
| 字段歧义（同名不同义） | 以数据字典为准；字典缺失则两个口径都给并标注 |
| 重复记录 | 先判断是真实重复还是连接膨胀；真实重复按主键去重并记录条数变化 |
| 类型不一致（数值列混入文本） | 用 `profile` 的 `dirty_numeric_count` 定位，逐条判定是缺失还是错录 |
| 单位不一致 | `scale_warning` 命中即按数据字典换算，换算公式写进 change_log |

### 7. 诚实输出
```bash
python3 scripts/data_tool.py schema /app/output/result.json
```

## result.json 契约

```json
{
  "case_id": "", "status": "pass|issues|partial|failed",
  "questions": [{"id": "Q1", "answer": "...", "evidence": ["data.csv:value 列求和", "行 12-45"]}],
  "aggregates": [{"column": "value", "op": "sum|count|mean|min|max", "value": 0, "group_by": null}],
  "data_dictionary": {"value": "测量值，单位 mg/L"},
  "lineage": {"snapshot": "snap-2026-11-20", "tables": ["data.csv"], "filters": [], "join_keys": []},
  "gain": {"baseline_accuracy": null, "skill_accuracy": null, "rework_rounds_saved": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
不手填数字、不跳过画像、不省略快照版本。每个上报数值都要能被 `recheck` 重算出来。

## 本课题聚焦
本题聚焦**清洗**：缺失、异常值、重复、类型不一致、单位不一致逐类给判定规则与处置动作，并给出「清洗前后条数对照」。清洗规则要能重跑，不得手工临时改数；哪些行被剔除、为什么剔，必须可逐条追溯。
