# 评分维度覆盖与证据

| 维度 | 已实现的可复核能力 | 证据入口 | 尚需平台/人工 |
|---|---|---|---|
| 实际效果 40 | 完整多文体成稿流程；quote 逐字回原文+行/字段；数字/单位/图表/引用和 required 保留；论断强度；逐段 before/after/reason | `transfer_check.py evidence/audit/result`；evidence/audit/result 三类报告 | 固定 3 案例的任务完成度、学科语义和实际排版质量 |
| 使用增益 25 | 机检直接返回行号/证据 id，减少通读核对；gain 强制同输入、约束、权限、预算与输入哈希 | result gain schema；bench 的 local_fixture 路径对照 | 真实基础 Agent 的质量、人工编辑条目、返工轮次；无 baseline 不声称提升 |
| 创新增益 15 | 受众画像→取舍→边界→多文体映射链条；术语锁定；冲突组；涉密发布闸；逐段覆盖 | `docs/positioning.md`；三命令与变异夹具 | 新学科表达的召回率与用户对流程的接受度 |
| 可靠体验 10 | partial 先行、分章落盘；题面五类异常均有识别信号+动作；缺材料/无法判断/运行失败分离；200 段稳定性 | SKILL 异常表；bench 第 20 项 | 扫描 PDF、损坏材料、服务故障等真实环境覆盖 |
| 生态贡献 10 | SKILL、project/brief/多文体/result 模板、最小示例、清单、格式/边界/评分文档、20 项 bench | `templates/`、`examples/`、`checklists/`、`bench/` | GitHub 公开链接需提交者提供并匿名访问验证 |

## 诚实状态

- 本地 **20/20** 断言证明的是脚本规则与回归，不是固定案例得分。
- 数值核查采用“复制原文表面形式”的严格策略，减少误换算，但合法等价改写也可能需要补底账。
- 干净稿需由 review 稿仅删标签生成；复杂 Office/PDF 视觉导出不是本题选择的突破点。
