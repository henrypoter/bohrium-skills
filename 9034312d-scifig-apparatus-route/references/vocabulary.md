# 图元词汇表与连接语义（装置图 / 技术路线图）

机器判据单一事实源：`assets/connection_rules.json`（渲染与 verify 共用）；本文件为文字说明。

## 1. 部件类型（node.type）
`unit` 工艺单元（反应器/塔/柱/混合器）；`source` 源头（气瓶/储罐/泵）；`sink` 终点（收集瓶/尾气/废液）；`default` 其他（阀/MFC/传感器/热电偶）；`milestone` 菱形（里程碑）。同类部件 label 加序号。
**source 双通道写法**：`{"locator":"句3","quote":"材料逐字片段(≤30字)"}`；locator 支持 `句N`/`SN`、`句N-句M`、`L0003[-L0005]`。verify 双通道核验：quote 归一化后须在材料中（找不到=疑似编造 fail）且落在 locator 区间（他处找到=位置错配 fail）；旧字符串 source 仅 warn。label/caption 实体片段须逐字见于材料（去括号/步骤编号），未命中给 difflib top-3 建议。spec.required 抄题面点名必做项，缺失强制 status=partial。
**edge source 同款**：每条边都带 source，且 locator 段落须支撑 from→to 方向（段落内 from 实体先于 to 实体）；反序=fail 矛盾，依据缺失→降级 unknown 并进 uncertainty，不臆造。

## 2. 连接语义（edge.style，禁换义）
`sequence` 步骤顺序：实线深灰，编号 1..N；`material` 物料流：实线蓝；`energy` 能量/加热：长虚线橙；`info` 信息/控制：点线绿；`reflux` 回流/循环：点划线灰。

## 3. 禁止与降级
禁凭空补连接（未写明的管路不画，标 uncertainty）；禁断头箭头（check 强制）；分流/合流画真实节点；参数缺失用 workorder `not_stated` 明示，冲突列 candidates；流向存疑降级 unknown/需确认，不画成有依据的定向流。接口须以 workorder id 对齐，介质/方向冲突不得布图；歧义保守串行必须写 decision，未决则 partial。

## 4. 泳道与编号规则（route）
lanes=阶段（上→下=推进）；同 lane 内 order 左→右；sequence=主序列/跨阶段依赖；并行=同 order 并列；里程碑 type=milestone。verify 校验编号==1..N 且 caption_steps 数量==sequence 边数（记 issue 不阻断）。

## 5. 导出规范
SVG 分层 layer-lanes/edges/entities/labels/legend/title；节点 id=node-* 带 data-source/data-quote；边 id=edge-N 带 data-style/data-from/data-to/data-source/data-quote；字体栈 Arial/Helvetica/PingFang SC/Microsoft YaHei/Noto Sans CJK SC/sans-serif（不嵌）；PNG 走回退链，全失败写 preview_unavailable。verify 六类检查点（实体逐字/连接语义/方向/图例/布局/导出）+渲染回读，另产 figure.verify.json（含 figure.score 0–100，停止条件：先修 fail 再修 warn，score≥90 或剩余 warn 均可解释即停）与 figure_map.md（人可读来源映射表+方向依据）；result.json 的 outputs 按 editable_source/preview/mapping/report 角色列举。

## 6. 工单审计与版本
`python3 scripts/workorder_guard.py audit spec.json <材料...> --require --out workorder.audit.json` 是布图前硬闸；schema 与字段例见 `examples/workorder_spec.example.json`。错误（接口/来源/顺序冲突）必须修；limitation（参数未给、接口未知、歧义保守取舍/未决）允许保留诚实 partial，但不可升级为 success。结果须携 source/artifact SHA-256、工具/图稿/spec 版本与复跑命令；科学结论不由机器通过代替。
