# 字段、执行与复算模板（复制到工作区后填写）

> 本模板是空结构，不是正式案例字典。所有值须从实际输入/字典获得。

## 1. 输入与字段字典

| 输入路径 | SHA256 | 来源/版本 | 编码 | 行数 | 主键 |
|-|-|-|-|-:|-|
|  |  |  |  |  |  |

| 物理字段 | 任务字段 | 含义 | 类型 | 单位 | 编码/合法范围 | 缺失哨兵 | 转换公式与依据 |
|-|-|-|-|-|-|-|-|
|  |  |  |  |  |  |  |  |

硬约束：字典未授权的哨兵不得排除；编码类别不得当连续值；单位换算须保留公式、原值和新值。

## 2. 清洗记录

| step_id | 输入哈希/行数 | 规则（含键、筛选） | 排除/修改字段与原值定位 | 输出行数/哈希 | 交人工项 |
|-|-|-|-|-:|-|
| S1 |  |  |  |  |  |

## 3. aggregates 声明

```json
{
  "id":"a1", "column":"value", "op":"mean", "value":0,
  "where":{"group":"treat"}, "group_by":null,
  "missing_values":[""], "drop_duplicates":["sample_id"],
  "tolerance":1e-9
}
```

将实际计算值填入 `value` 后必须运行 `recheck`。分组 `value` 用 `{"组名": 数值}`；`row_count` 的 `column` 可为 `null`。复杂筛选先输出派生 CSV，并记录其输入、代码和哈希。

## 4. SQL 与基数核验

```sql
-- 实际执行并留存，不把示例数字当答案
SELECT COUNT(*) FROM a;
SELECT COUNT(*) FROM a JOIN b ON a.id=b.a_id;
SELECT COUNT(DISTINCT a.id) FROM a JOIN b ON a.id=b.a_id;
```

| query_id | 连接键与关系 | 连接前/后行数 | 去重主键数 | SQL | columns/rows 结果哈希 |
|-|-|-:|-:|-|-|
| Q1 |  |  |  |  |  |

空结果须记录 `empty_result=true` 和诊断筛选，不得自动放宽正式查询。写操作拒绝；只读复跑失败时保留原始 SQLite 错误。

## 5. 图表 series 映射（任务有图时）

| figure/series | 源字段/op/筛选/缺失口径 | 上报值 | 坐标轴标目/单位 | 误差定义 | 图件路径/SHA256 |
|-|-|-:|-|-|-|
| F1/S1 |  |  |  | SD/SEM/无 |  |

`chartcheck` 只自动核验已声明聚合系列；散点逐点或像素检查未覆盖的部分写入 `unchecked`。

## 6. 运行、证据、增益与交付清单

- [ ] `run-log.json` 有真实命令、代码/输入/产物哈希、解释器/平台/依赖版本、种子、退出状态和报错。
- [ ] 每个 `questions[].evidence[]` 有 `artifact/location`，并有原文 `quote` 或源 `sha256`。
- [ ] `recheck` 全绿；有聚合图则 `chartcheck` 全绿；有 SQLite 则 `sqlcheck` 全绿。
- [ ] `coverage` 五项均为 `pass/issues/not_checked`，未做的附原因。
- [ ] 两臂对照保持输入、权限、环境、预算一致；无基础臂证据就 `not_checked`，差不填估值。
- [ ] `schema` 全绿；`status=pass` 时 `unchecked` 与 `uncertainty` 必须为空。
