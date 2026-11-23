# 跨站流程规格（flow_spec.md）

## 步骤表
| id | 步骤 | 依赖 | 输入 | 输出 | 状态 |
|-|-|-|-|-|-|
| W1 | 检索下载 | — | query | files[] | done |
| W2 | 字段抽取 | W1 | files[] | rows[] | done |
| W3 | 写入目标 | W2 | rows[] | ids[] | pending |

## 跨站交接
| 源 | 源字段 | 目标 | 目标字段 | 转换 | 权限 | 源条数 | 目标条数 |
|-|-|-|-|-|-|-|-|
| 文献库 | title | 笔记 | name | 去标签 | green | 10 | 10 |

- 权限：green 直传 / yellow 脱敏后传 / red 禁止外传（哈希代替）。
- 迁移前后条数必须相等，不等即丢数据/重复。

## 幂等与续跑
- 每步一个 idempotency_key，重复执行不产生第二条记录。
- failed 步骤写 resume_point，续跑不重跑已完成步骤。
