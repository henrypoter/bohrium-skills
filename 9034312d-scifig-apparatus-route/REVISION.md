# 修订说明（实验装置与技术路线图）

## 判对标准对齐

- **实体可追溯**：沿用 node/edge `{locator,quote}` 双通道；workorder 中参数、接口、顺序断言也做“材料存在 + 区间内命中”。未发现/错配是 error，不用近似措辞代替来源。
- **连接与顺序成立**：新增 `scripts/workorder_guard.py audit`，检查接口重复/悬空/端点错配、介质冲突、in/out 方向冲突，以及工艺 A→B/B→A 和依赖环。原 SVG glyph/端点/编号检查保留。
- **可修改与复跑**：保留分层 SVG + 真实预览；`result.json` 新增 result/spec/figure 版本、输入与产物 bytes+SHA-256、工具版本、复跑命令和原 `output_contract` 逐键字段。缺产物保持 null 并列 `output_contract_null_fields`。

## 本次新增文件

- `scripts/workorder_guard.py`：纯标准库工单审计命令。
- `bench/workorder_bench.py`：正向零误杀 + 13 类定向变异/兼容性/集成检查，38 项断言（含 v2 result schema 正向/坏哈希）。
- `examples/workorder_spec.example.json`、`examples/workorder_material.example.txt`：明确标为自拟示例，不是官方案例答案。

修改 `scripts/scifig.py` 将 workorder 审计内嵌 verify，并在 result 中执行 limitation/error 的 status 门控；`scripts/fig_tool.py schema` 同时接受 legacy 和真实 v2 result，坏 manifest 哈希会失败。旧无工单 spec 仍兼容，正式工作流用 `--require` 禁止漏审。

## 异常处置补强

- **部件参数缺失**：`not_stated + reason`，保留事实图但 completion/status 为 partial；不填行业默认值。
- **参数冲突**：`conflicted + candidates + sources`，列全不同候选；候选不全直接 error。
- **工艺描述歧义**：`conservative_choice` 必须写 decision，`unresolved` 保留人工确认；两者均禁止 success。
- **接口信息冲突**：介质、方向、所属节点和引用逐项给机器 code；错误先修，未知则诚实 partial。
- 字体缺失、导出失败、画布溢出、来源缺失/无法判断/运行失败均在 SKILL 异常表分别给动作，不概括为“注意”。

## 相对基础 Agent 的边界与增益

基础 Agent 可以从文本画图，但通常没有可执行的参数/接口/顺序一致性闸，也难以证明修改某条边后重新核过来源。当前 Skill 的增量是**可机检一致性、诚实分级、可复跑身份**，不是自动生成科学事实。抽取仍需 Agent 读实际材料；工单只能检查已显式声明内容，不能证明无遗漏，也不判断实验方案合理性。SVG/PDF/PNG 可用不代表科学正确，最终语义仍由原生/LLM Judge 或人工复核。

## 可复现证据（均为自拟 fixture，不是平台成绩）

```bash
python3 scripts/selftest.py          # 基线全链路 + 旧变异全绿
python3 bench/bench_run.py          # fig_tool 8/8
python3 bench/workorder_bench.py    # 新工单闸与 v2 schema 38/38
```

未运行平台固定三案例，未声称超过基础 Agent 或榜首；质量/效率增益须由平台同输入对照确认。
