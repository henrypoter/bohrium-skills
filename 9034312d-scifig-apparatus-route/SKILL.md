---
name: scifig-apparatus-route
description: 实验装置与技术路线图科研绘图。材料→实体—连接—步骤—流向 spec.json→分层可编辑 SVG；workorder_guard 专项审计部件参数缺失/冲突、接口介质与方向冲突、工艺歧义和顺序环，verify 六类检查点+来源双通道+required 覆盖，result.json 带版本/SHA-256/复跑命令/output_contract 对齐，异常诚实降级。纯标准库。
---

# 实验装置与技术路线图 Skill（scifig）

## 1. 用途与适用
把 /input 材料转成实体可追溯、箭头方向有依据、编号与正文一致的装置/路线图，交付分层 SVG + figure_map.md + 连接关系表 + PNG。无可画实体 status=failed。先读实际文件，不凭文件名/标签臆测。

## 2. 预算与停止条件（硬性）
每案例 ≤12 请求、≤600 秒；S0 先落盘 partial result.json。
停止条件：先修 fail 再修 warn；figure.score≥90 或剩余 warn 均可解释即停。

## 3. 六步流程（/app/work 工作，/app/output 产出）
1. 读材料：读 /input 材料定 kind，把题面点名必做项抄入 spec.required。
2. 抽 spec + 工单：nodes/edges 带 `source={locator,quote}`；edge quote=支撑 A→B 方向的材料片段。新增 `spec.workorder`（照 `examples/workorder_spec.example.json`），逐项登记 `parameters/interfaces/order_assertions/ambiguities`；**未写明的连接不画，无依据方向标 unknown**。
3. 工单闸：`python3 scripts/workorder_guard.py audit spec.json <材料...> --require --out /app/output/workorder.audit.json`。接口冲突/quote 错配/顺序环=error 必须先修；参数未给、接口未知、工艺保守选择/未决=limitation，保留产物但禁 success。
4. build + check：`python3 scripts/scifig.py render spec.json /app/output/figure.svg`；`python3 scripts/scifig.py verify spec.json /app/output/figure.svg <材料...>` 出 figure.verify.json + figure_map.md。若 spec 含 workorder，verify 自动内嵌同一审计；按 §2 修 fail。
5. export：`preview` 出 PNG（rsvg-convert→inkscape→ImageMagick→PyMuPDF，全失败 preview_unavailable）；先检查画布溢出，失败不得伪写成功。
6. result：`result ... --case /input/case.json --source <材料> --workorder-audit ...` 汇总原 output_contract、版本、输入/产物 SHA-256 和复跑命令。

## 4. spec.json（示例见 examples/*.example.json）
字段：kind(apparatus|route)、nodes[id,label,type,source]、edges[from,to,style,label,source]、lanes(route)、caption_steps、required。apparatus 节点加 x,y,w,h；route 加 lane,order。style 五种见 connection_rules.json；sequence 边按序编号 1..N。
source 双通道：{"locator":"句3","quote":"≤30字逐字片段"}；locator 支持 句N/SN、句N-句M、L0003[-L0005]。verify：quote 归一化(NFKC/空白折叠/连字符换行/大小写)后须在材料(找不到=fail 疑似编造)且落在 locator 区间(他处=fail 错配)；旧字符串 source 仅 warn。edges 的 source 同款，且其 locator 段落须支撑 from→to 方向（段落内 from 实体先于 to 实体出现；反序=fail 矛盾；依据缺失→降级 unknown，不臆造）。

**workorder_schema=scifig-workorder/1.0**：`parameters[]`= `{id,node,name,status,value,unit,source,reason,candidates}`，status 仅 `stated/not_stated/not_applicable/conflicted`；`interfaces[]`=`{id,node,port,medium,direction:in|out|bidirectional|unknown,source}`，edge 以 `from_interface/to_interface` 引用；`order_assertions[]`=`{before,after,source}`；`ambiguities[]` 状态 `resolved/conservative_choice/unresolved`。完整可运行字段例见 `examples/workorder_spec.example.json`。机检：接口 id/node+port 不可重复，介质一致且 out→in，before/after 不成环；conflicted 参数须列出至少两个带来源候选；任何 limitation 都 sets `completion_ceiling=partial`。

## 5. 输出契约
result.json：case_id/status/summary/figure_kind/outputs/sources/data_mapping/connections/changes/change_records/uncertainty/checks/generator；v2 另含 `result_schema_version`、`figure_version`、`spec_schema_version`、`generated_at_utc`、`tool_versions`、`source_manifest`、`artifact_manifest`（真实文件 bytes+SHA-256）、`reproduction.commands`、`review`、`output_contract` 与 `output_contract_null_fields`。传 `--case /input/case.json` 时原 output_contract 每键都出现；无对应真实产物保持 null 并列名，不拿说明文字冒充产物。接口/歧义未闭合或 verify=issues/invalid 时 status 强制 partial。
- outputs 按角色：editable_source(分层 SVG)/preview(PNG)/mapping(figure_map.md)/report(figure.verify.json 含 score)/exports。
- SVG 分层：layer-lanes/edges/entities/labels/legend/title；节点 id=node-* 带 data-source/data-quote；边 id=edge-N 带 data-style/data-from/data-to/data-source/data-quote；字体栈 Arial/Helvetica/PingFang SC/Microsoft YaHei/Noto Sans CJK SC/sans-serif。
- verify 六类检查点：实体逐字(未命中给 difflib top-3)/连接语义(style→stroke/dash/箭头)/方向(箭头 A→B 在来源段落有依据)/图例(只用到的线型)/布局(dangling/orphan/overflow)/导出(SVG well-formed+分层+字体栈)；另保留 quote 双通道、required 覆盖审计(status 门控)、trace 数值单位、numbering 编号-图注。figure.score 0–100 收官。
- figure_map.md：组件/连线 → locator+quote+命中状态 + 箭头方向依据 + required 覆盖率。
- sources=覆盖率摘要（含方向 supported/unknown/unsourced/contradicted）；changes={decisions,human_review}；uncertainty 存缺口与方向降级。

## 6. 异常降级
| 情况 | 识别/处置 | 完成状态 |
|-|-|-|
| 部件参数未给 | workorder `not_stated`+reason；只画已给值，不填常见默认值 | limitation→partial |
| 参数值/单位冲突 | `conflicted`+至少两个带来源 candidates，不擅自择一 | limitation→partial；候选不全=error |
| 接口未指定/未知 | edge 缺接口引用或 direction/medium=unknown，保留可画主结构 | limitation→partial |
| 接口介质/方向/端点冲突、引用悬空 | 返回 `interface_*_conflict/reference_unknown`，先修工单和边 | error→partial，禁 success |
| 工艺分支/先后歧义 | `conservative_choice` 必须记录 decision；无法取舍用 `unresolved`，不默认补并行 | limitation→partial |
| 工艺 A→B 与 B→A/依赖环 | `process_order_conflict/cycle`，停止自动编号并回原文 | error→partial |
| quote 找不到/错配 | fail：回原文复制 quote、修 locator；材料没有则删图元 | error→partial |
| 箭头方向无依据 | 降级 unknown + uncertainty，不臆造箭头 | partial/需确认 |
| 实体名材料外 | 给 difflib top-3；不得把建议当来源 | warn/partial |
| required 未覆盖 | 缺项保留在 required.missing | 强制 partial |
| 字体缺失 | 使用字体栈，记录实际 renderer；不要把“字体嵌入”写成已通过 | warn；预览仍须真实生成 |
| 渲染器全缺/导出失败 | preview_unavailable+原因，SVG 保留；不伪造 PNG/PDF | partial |
| 画布溢出/重叠 | 调 x/y/w/h 或拆图后重跑 verify，不裁掉科学实体 | partial，修后重验 |
| check errors/SVG 无法解析 | 阻断修 spec；无法修复则给 partial | failed/partial |
| 材料缺失、无法判断、运行失败 | 三者分别记 uncertainty，不混写“成功但有限制” | partial/failed |

## 7. 方法改进
1. 判据外置 connection_rules.json（渲染+verify 共用）；2. advisory 六类检查点+渲染回读不误杀；3. 实体与箭头双通道锚定 + 实体逐字 + required 门控；4. figure.score+停止条件；5. spec 中间表示解耦图面，泳道/自动编号；6. 参数/接口/顺序/歧义工单先审再布图，错误与“不确定但可交付”分级；7. 输入和产物哈希+复跑命令让图谱版本可独立复核。

## 8. 最小调用示例（示例，非正式案例结果）
```bash
python3 scripts/workorder_guard.py audit examples/workorder_spec.example.json examples/workorder_material.example.txt --require --out /app/work/workorder.audit.json
python3 scripts/scifig.py render examples/workorder_spec.example.json /app/output/figure.svg
python3 scripts/scifig.py verify examples/workorder_spec.example.json /app/output/figure.svg examples/workorder_material.example.txt
# 原有无工单示例仍兼容：
python3 scripts/scifig.py render examples/apparatus_spec.example.json /app/work/apparatus.svg
python3 scripts/scifig.py verify examples/apparatus_spec.example.json /app/work/apparatus.svg examples/apparatus_material.example.txt
python3 scripts/scifig.py result --case-id demo --spec examples/apparatus_spec.example.json --svg /app/work/apparatus.svg --verify /app/work/apparatus.verify.json --source examples/apparatus_material.example.txt --status success --summary 示例 --out /app/output/result.json
python3 scripts/selftest.py
python3 bench/workorder_bench.py   # 工单正向零误杀 + 参数/接口/歧义变异
```
check/preview 见 §3；路线图换 examples/route_spec.example.json + route_material.example.txt；变异夹具 examples/route_spec.mutation.example.json（verify=issues exit 0）。

## 9. 限制与维护
布局网格/泳道，不做美学寻优；复杂装配手调 x/y。不嵌字体(字体栈防御)；无外部依赖；改线型只改 connection_rules.json。quote/方向核验依赖材料文本可读(PDF 先抽文本)；locator 无法解析时方向核验退到全材料存在性并记 warn。工单只能检查已显式抽取的参数/接口/顺序，不证明抽取本身无遗漏，也不证明实验方案科学合理；科学判断仍由材料、人工或 Judge 完成。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`workorder_guard` 核参数/接口/顺序和来源，`scifig.py verify` 核实体、连接、编号、布局；`fig_tool.py svg_check` 查文字转曲、尺寸和空图，manifest+复跑命令供独立复核。
- **使用增益（25 分）**：不预写或捏造 `gain`；质量/耗时/返工差值只能由平台同输入、同预算的基础 Agent/Skill 对照生成，当前 Skill 提供可定位的检查记录作为证据入口。
- **创新增益（15 分）**：结构化 spec + 参数/接口/歧义工单先审再布图，冲突与未知分级并进入 status 门控。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/figure_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/figure_spec.md`、工单示例与 `bench/bench_run.py`、`bench/workorder_bench.py` 可直接复用维护。

### 交付前自检
```bash
python3 bench/bench_run.py   # 原有工具正向零误杀 + 变异必命中
python3 bench/workorder_bench.py
```
