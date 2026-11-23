# 修订说明（重做）

本题 v1 因 harness evaluation_error 无分。本轮**重做**（非修改），换跨站专用方案：

- 专用工具 `crosssite_tool.py flow_check`：DAG 无环、状态合法、**字段映射显式**、**权限分级 green/yellow/red**、**迁移前后条数闭合**、幂等键唯一、失败有续跑点。
- 迁移完整性：`source_count == target_count` 机检，丢数据/重复直接失败。
- 权限分级：red 字段禁止外传（哈希代替），不笼统说"注意安全"。
- 异常处置 6 行：登录失效/元素缺失/超时限流/权限拒绝/同步冲突/迁移条数不符。
- 模板 `templates/flow_spec.md` 可复用。
