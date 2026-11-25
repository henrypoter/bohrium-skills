# 修订说明（v2 → v3）

本轮不是增加自述，而是把“能不能开工”落成标准库命令、`result.json` 硬约束和变异测试。未改共享核心，未生成组织方正式案例答案，未伪造平台基线或评分。

## 1. 实际效果（40）：七类审查、资源算术、参数反推、版本证据闭环

- `audit`：从 v2 六类提升到题面七类，逐类要求唯一定位、状态、结论、证据；缺失写 `not_checked + reason`，条件可行必须有可执行条件，fail/not_checked 不得被总体结论掩盖。
- `resources`：新增设备/材料四态、可用设备精度/附件、采购货期、样本缺口校验。成本执行逐行乘法与总额求和；排期执行单步时长、并行组关键路径和采购前置等待计算，输出预算/工期/样本的可复算值。
- `params --spec`：同名多约束数组取 `max(min)` / `min(max)`，核对结果中的 `derived_min/max`，并检查推荐值、单位、步进、互斥、空交集和非有限数，不再只查单设备上下限。
- `verify --source-root`：实际读取源文件，验 SHA-256、JSON Pointer 值或逐字文本引文；防目录越界。结果新增 `result_schema_version/tool_version/input_digest/permissions_digest` 和源版本，判断定位到字段/行。
- 交付命令失败统一 JSON 非零退出并给降级动作，不能把未运行当通过。

## 2. 使用增益（25）：公平对照而非口头增益

`gain BASELINE SKILL --out` 强制双方 `case_id/input_digest/permissions_digest` 一致，按同一七类口径计算检查覆盖、定位判断和异常覆盖；只有双份真实 telemetry 才记用时、返工、补材料轮次。缺平台基线时必须 `not_run + reason`。该设计保留质量与效率的可核验增益，但不把 bench 当平台分数。

## 3. 创新增益（15）：基础 Agent 难稳定完成的确定性能力及边界

- 多来源限值交集与步进反推：能证明“推荐点为何可行/为何无人选”，但不会发明单位换算、材料阈值。
- 采购等待+并行组关键路径+分项预算联动：把技术审查落到真实资源约束；复杂日历、非线性能耗和资源抢占仍需专用排期系统。
- 机器可验的版本/逐字引文闭环：可查出方案换了还是审查引文错了；PDF 引文需真实提取文本，图片语义仍交人工。
- 异常逐项绑定七类审查和处置责任人：比泛泛“注意安全”可执行；不替代设备、安全或伦理批准。

## 4. 可靠体验（10）：题面失败情形全覆盖

异常寄存器现在强制十条且每条含识别信号、动作、处置类型、负责人和检查绑定：

`plan_missing_pages`、`missing_parameters`、`unknown_equipment`、`ethics_undetermined`、`internal_contradiction`、`oversized_document`，以及设备故障、材料批次差异、样本量不足、参数越界。bench 对未核验无理由、伦理待定无动作、未知设备缺精度等变异均要求命中。

## 5. 生态贡献（10）：最小示例、模板、文档、复用脚本、bench

- 更新 `SKILL.md` 完整调用、契约、公式、限制和异常表。
- 更新 `templates/plan_spec.md` 为七类审查+资源/排期/预算+证据模板。
- `bench/fixtures/example_input.json`、`good_result.json`、`limits.json` 是明确标识的合成最小示例，不是正式答案。
- `bench/bench_run.py` 共 **33 项**，覆盖 `audit/schema/resources/params/verify/gain` 的正向零误杀与变异必命中；最终运行 **33/33 PASS**。

## 仍未消除的差距

没有组织方三例正式输入、原生基础 Agent 轨迹或榜首运行产物，本轮只能证明工具与合成变异行为，不能声称超过榜首。正式三例上的长文档定位成功率、真实异构单位体系、复杂 PDF 表格/图片证据和专家规则覆盖仍需平台运行验证；GitHub 附加分取决于既有公开链接是否有效，本轮未联网虚构链接。
