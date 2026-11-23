---
name: scifig-apparatus-route
description: 实验装置与技术路线图科研绘图。抽实体—连接—步骤—流向为 spec.json，渲染分层 SVG(layer-entities/edges/labels/legend)，verify 六类检查点(实体逐字/连接语义/方向/图例/布局/导出)+渲染回读+figure.score 收官；实体与箭头均 {locator,quote} 双通道锚定(quote 找不到=疑似编造 fail、错位=fail；箭头方向依据缺失→降级 unknown 不臆造)，required 覆盖审计，figure_map.md 人读映射，回退链出 PNG，result.json 按角色列举。纯标准库。
---

# 实验装置与技术路线图 Skill（scifig）

## 1. 用途与适用
把 /input 材料转成实体可追溯、箭头方向有依据、编号与正文一致的装置/路线图，交付分层 SVG + figure_map.md + 连接关系表 + PNG。无可画实体 status=failed。先读实际文件，不凭文件名/标签臆测。

## 2. 预算与停止条件（硬性）
每案例 ≤12 请求、≤600 秒；S0 先落盘 partial result.json。
停止条件：先修 fail 再修 warn；figure.score≥90 或剩余 warn 均可解释即停。

## 3. 五步流程（scripts/scifig.py；/app/work 工作，/app/output 产出）
1. 读材料：读 /input 材料定 kind，把题面点名必做项抄入 spec.required。
2. 抽 spec：nodes 带 source={locator,quote}；**每条 edge 带 style 与 source**——edge quote=支撑 A→B 方向的材料片段，locator 钉住来源段落；未写明的连接不画，方向无依据的边标 unknown 进 uncertainty。
3. build：`render spec.json /app/output/figure.svg` 出分层 SVG。
4. check：`verify spec.json figure.svg <材料...>` 六类检查点+渲染回读，出 figure.verify.json + figure_map.md；按 §2 修到 score≥90。
5. export：`preview` 出 PNG（rsvg-convert→inkscape→ImageMagick→PyMuPDF，全失败 preview_unavailable）；`result ...` 汇总契约字段。

## 4. spec.json（示例见 examples/*.example.json）
字段：kind(apparatus|route)、nodes[id,label,type,source]、edges[from,to,style,label,source]、lanes(route)、caption_steps、required。apparatus 节点加 x,y,w,h；route 加 lane,order。style 五种见 connection_rules.json；sequence 边按序编号 1..N。
source 双通道：{"locator":"句3","quote":"≤30字逐字片段"}；locator 支持 句N/SN、句N-句M、L0003[-L0005]。verify：quote 归一化(NFKC/空白折叠/连字符换行/大小写)后须在材料(找不到=fail 疑似编造)且落在 locator 区间(他处=fail 错配)；旧字符串 source 仅 warn。edges 的 source 同款，且其 locator 段落须支撑 from→to 方向（段落内 from 实体先于 to 实体出现；反序=fail 矛盾；依据缺失→降级 unknown，不臆造）。

## 5. 输出契约
result.json：case_id/status/summary/figure_kind/outputs/sources/data_mapping/connections/changes/change_records/uncertainty/checks/generator。
- outputs 按角色：editable_source(分层 SVG)/preview(PNG)/mapping(figure_map.md)/report(figure.verify.json 含 score)/exports。
- SVG 分层：layer-lanes/edges/entities/labels/legend/title；节点 id=node-* 带 data-source/data-quote；边 id=edge-N 带 data-style/data-from/data-to/data-source/data-quote；字体栈 Arial/Helvetica/PingFang SC/Microsoft YaHei/Noto Sans CJK SC/sans-serif。
- verify 六类检查点：实体逐字(未命中给 difflib top-3)/连接语义(style→stroke/dash/箭头)/方向(箭头 A→B 在来源段落有依据)/图例(只用到的线型)/布局(dangling/orphan/overflow)/导出(SVG well-formed+分层+字体栈)；另保留 quote 双通道、required 覆盖审计(status 门控)、trace 数值单位、numbering 编号-图注。figure.score 0–100 收官。
- figure_map.md：组件/连线 → locator+quote+命中状态 + 箭头方向依据 + required 覆盖率。
- sources=覆盖率摘要（含方向 supported/unknown/unsourced/contradicted）；changes={decisions,human_review}；uncertainty 存缺口与方向降级。

## 6. 异常降级
| 情况 | 处置 |
|-|-|
| 参数/接口不全 | 只画材料写明的 |
| 分支/先后不明 | 保守串行 + uncertainty |
| quote 找不到/错配 | fail：修 spec 重验 |
| 箭头方向无依据 | 降级 unknown + uncertainty 标注 |
| 实体名材料外 | warn + top-3 建议 |
| required 未覆盖 | status 禁 success/complete→partial |
| check errors/SVG 无法解析 | 阻断修 spec，保持 partial |
| 渲染器全缺 | preview_unavailable+说明 |

## 7. 方法改进
1. 判据外置 connection_rules.json（渲染+verify 共用）；2. advisory 六类检查点+渲染回读不误杀；3. 实体与箭头双通道锚定 + 实体逐字 + required 门控；4. figure.score+停止条件；5. spec 中间表示解耦图面，泳道/自动编号。

## 8. 最小调用示例（示例，非正式案例结果）
```bash
python3 scripts/scifig.py render examples/apparatus_spec.example.json /app/output/figure.svg
python3 scripts/scifig.py verify examples/apparatus_spec.example.json /app/output/figure.svg examples/apparatus_material.example.txt
python3 scripts/scifig.py result --case-id demo --spec examples/apparatus_spec.example.json --svg /app/output/figure.svg --preview /app/output/figure.png --verify /app/output/figure.verify.json --status success --summary 示例 --out /app/output/result.json
python3 scripts/selftest.py
```
check/preview 见 §3；路线图换 examples/route_spec.example.json + route_material.example.txt；变异夹具 examples/route_spec.mutation.example.json（verify=issues exit 0）。

## 9. 限制与维护
布局网格/泳道，不做美学寻优；复杂装配手调 x/y。不嵌字体(字体栈防御)；无外部依赖；改线型只改 connection_rules.json。quote/方向核验依赖材料文本可读(PDF 先抽文本)；locator 无法解析时方向核验退到全材料存在性并记 warn。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/fig_tool.py svg_check figure.svg` 查文字是否转曲、尺寸是否缺失、是否空图；`element_map` 查每个元素是否映射到来源数据。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：文字不转曲的可编辑源、元素-数据映射、导出前合规检查。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/figure_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/figure_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
