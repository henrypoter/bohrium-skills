---
name: scientific-figure-domain
description: 覆盖科研绘图全部任务：示意图/数据图表/机制通路/装置路线，统一以文字不转曲+元素-数据映射+双交付为机检底座
---

# 科研绘图领域总课题

## 领域总览与任务分诊

覆盖科研绘图全部任务：示意图/数据图表/机制通路/装置路线，统一以文字不转曲+元素-数据映射+双交付为机检底座

**先分诊、后执行**：读输入判定属于哪个子任务，再走下方统一核心流程；子任务的专属交付要点见下表右列。

| 子任务 | 触发信号 | 交付要点 |
|-|-|-|
| 科研示意图生成与编辑 | 示意概念 | 实体关系+可编辑源 |
| 科研数据图表生成与编辑 | 数据出图 | 编码正确+数据映射 |
| 生物机制图与通路图 | 机制/通路 | 层级+方向+比例 |
| 实验装置与技术路线图 | 装置/流程 | 结构+流向+标注 |


从材料走通「材料→图稿→导出」，产出科学成立、**可继续编辑**的图。不适用：纯装饰插画、替代专业绘图软件的全部功能。

## 调用
- 输入：`/input/case.json` + 数据/材料 + `task.md`
- 输出：`/app/output/result.json` + 可编辑 SVG 源 + 渲染 PNG
- 工具：`scripts/fig_tool.py`（`svg_check` / `element_map` / `schema`）
- 模板：`templates/figure_spec.md`

## 工作流

### 0. 选图型与编码
按数据类型与目的选图型；编码不夸大差异（面积、角度、双轴慎用）。

### 1. 生成可编辑源（关键：文字不转曲）
生成 SVG 时**文字必须保留为 `<text>` 元素**，不得转成 path——转曲就不可编辑。
```bash
python3 scripts/fig_tool.py svg_check figure.svg
```
抓：无 `<text>` 却大量 `<path>`（文字已转曲）、缺尺寸（无 width/height 且无 viewBox）、元素过少（疑空图）。

### 2. 元素-数据映射（可核验的根本）
每个视觉元素（数据点、柱、线、标签）映射到来源数据与位置：
```bash
python3 scripts/fig_tool.py element_map mapping.json
```
抓：未映射元素、缺来源定位。图上每个数都要能回指到数据。

### 3. 标注与导出
图注独立可读（单位、图例、误差线定义、样本量、子图编号）。导出：可编辑 SVG + 渲染 PNG 预览，发表级（≥300dpi、字体嵌入）。

### 4. 增益对照
同材料、同画布、同导出参数，基础 Agent vs 本 Skill 各跑一次，报：科学正确性、图面规范、可编辑性、人工修改量。

### 5. 异常处置
| 异常 | 动作 |
|-|-|
| 来源缺失 | 该元素标 unknown，不臆造数据 |
| 描述矛盾 | 按数据为准并标注，列出矛盾点 |
| 数据与图例不符 | 记 critical，核对后重绘 |
| 字体缺失 | 用可嵌入的替代字体并声明，不乱码 |
| 导出失败 | 保留 SVG 源并记录失败原因，交部分产物 |

### 6. 诚实输出
```bash
python3 scripts/fig_tool.py schema /app/output/result.json
```

## result.json 契约
```json
{"case_id":"","status":"pass|issues|partial|failed","figure_version":"v1",
 "figures":[{"id":"F1","svg":"f.svg","png":"f.png","figure_type":"schematic"}],
 "mapping":[{"element":"rect1","source":"data.csv","source_location":"A列"}],
 "gain":{"baseline_editability":null,"skill_editability":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 底线
文字不转曲；每个元素映射到来源；可编辑 SVG + 渲染 PNG 双交付；图注独立可读。