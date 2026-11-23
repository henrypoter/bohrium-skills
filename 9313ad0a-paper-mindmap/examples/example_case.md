# 最小调用示例（以下材料与输出均为虚构示意，非正式案例结果）

## 1. 自拟短材料（虚构，仅供演示）
> §1 柔性传感器在可穿戴健康监测中需求增长，但灵敏度与拉伸性难以兼顾。本文研究裂纹结构对灵敏度的提升机制。
> §2 采用激光直写在 PDMS 上制备石墨烯薄膜（§2.1），在 0–30% 应变下测试电阻响应（§2.2）。
> §3 灵敏度系数 GF=152（应变 30% 时，§3 图2）；1000 次循环后信号漂移 <5%（§3 图3）。材料未给出响应时间数据。

## 2. 编写大纲 outline.md
```
# 裂纹结构柔性应变传感器
- 研究背景 {来源: §1}
  - 灵敏度与拉伸性难以兼顾 {来源: §1 第2句}
  - 研究问题：裂纹结构的增敏机制 {来源: §1 末句}
- 方法 {来源: §2}
  - 激光直写石墨烯/PDMS {来源: §2.1}
  - 0–30% 应变电阻测试 {来源: §2.2}
- 结果 {来源: §3}
  - GF=152 @30%应变 {来源: §3 图2} {关系: 支持} {关联: 0–30% 应变电阻测试}
  - 1000 次循环漂移<5% {来源: §3 图3}
- 结论与缺口
  - 裂纹结构提升灵敏度 {存疑: 结论由结果概括}
  - 响应时间数据缺失 {存疑: 材料缺口}
```
`{关联: <另一节点显示文本>}` 表达跨分支关系：写入 .mm 的 `<arrowlink>`、OPML 的 `_link` 属性，并在 SVG 上画红色虚线弧。

## 3. 调用
```
python3 scripts/build_map.py outline.md --outdir /app/output --name mindmap --title "示例导图"
```
预期打印：`OK nodes=13 sourced=9 depth=2 branches=4 readability=95/100 status=ok_with_warnings`（warning 1：E3「研究问题：裂纹结构的增敏机制」文字超 24 单位，可精简；warning 2：E1「结论与缺口」分支无 {来源}，属概括性分支，可保留并写入 uncertainty）。

## 4. 示意输出（示例标注，非真实案例结果）
/app/output 下得到：
- mindmap.mm：FreeMind 可编辑源，XMind/FreeMind 可导入；每个节点的来源/关系/存疑在 `<richcontent TYPE="NOTE">` 备注中，跨分支关系为 `<arrowlink DESTINATION=...>`，节点带稳定 ID。
- mindmap.opml：来源/关系/存疑/关联写入 `_source`/`_relation`/`_uncertain`/`_link`/`_note` 自定义属性。
- mindmap.svg：横向树预览，存疑节点虚线框、跨分支关系红色虚线弧，内置 CJK 字体栈。
- mindmap_mapping.md：13 行节点-来源-关系-关联映射。
- mindmap_report.json：warnings + 规则化 diagnostics + readability.score（0–100）。

result.json 示例骨架：
```json
{
  "case_id": "example-demo（示例）",
  "status": "success",
  "outputs": {
    "editable_source": ["mindmap.mm", "mindmap.opml"],
    "preview": "mindmap.svg",
    "mapping": "mindmap_mapping.md",
    "report": "mindmap_report.json"
  },
  "sources": {"sourced_nodes": 9, "total_nodes": 13, "locator_style": "章节/图表号"},
  "uncertainty": ["裂纹结构提升灵敏度：概括推断，无显式结论段", "响应时间数据缺失"],
  "changes": ["响应时间无法成节点，记入 uncertainty"]
}
```
