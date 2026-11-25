# 同输入同权限增益评分协议

本协议只定义如何计算，不提供正式白板或预制结果。平台未提供双方实测输出时，`gain.status=baseline_not_provided`，提升未知。

## 公平性硬门槛

基础 Agent 不加载本 Skill；Skill Agent 加载同一提交版本。两侧必须具有相同：
- 输入文件及 SHA256、任务说明和原始论文；
- 模型与解码设置、工具/网络/文件权限；
- 请求和 900 秒等预算、重复次数；
- 盲评规则与金标准版本。不得让 Skill 侧先看基础侧答案。

## 评分口径

1. 在运行前固定 gold 单元格及身份键。`total_cells` 为应评分单元格数，`correct_cells` 要求字段、值、单位、身份和来源均正确；缺失只有正确保持空缺才算对。
2. `false_merges` 单独计，不因其他单元格正确而抵消；精确重复漏合并可在人工修正条数中体现。
3. `manual_corrections` 是为达到交付要求而人工改的单元格/合并/冲突裁决条数，按同一清单计。
4. `runtime_seconds` 含读取、换算、复核和导出，不含平台另行暂停的服务故障。
5. 主指标 `cell_accuracy=correct_cells/total_cells`；报告绝对差，不把比例差写成百分点以外的“提升率”。

## 两侧指标 JSON

```json
{
  "run": {"input_sha256": "<64 hex>", "permissions": "<同一权限描述>",
          "model": "<同一模型/配置>", "budget_seconds": 900},
  "correct_cells": 0,
  "total_cells": 1,
  "false_merges": 0,
  "manual_corrections": 0,
  "runtime_seconds": 0
}
```

`gain` 子命令检查公平性和数值范围，计算 `delta.cell_accuracy` 的真实差值以及 false_merges/runtime/manual_corrections 差。基线为平台结果，不是参赛者答案。
