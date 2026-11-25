---
name: scientific-data-visualization
description: 科研数据可视化：按数据结构选型，标准库真渲染 SVG/300dpi PNG，自动生成图注，并从源 CSV 逐行复算和确定性重绘审计全部图元
---

# 科研数据可视化

目标不是“画一张漂亮图”，而是完成 **口径确认 → 图型选择 → 编码 → 标注/图注 → 发表级导出 → 逐元素回源审计**。不得只给“建议画柱状图”的文字，不得把数据库查询当成图件交付。所有新增工具只使用 Python 标准库。

不适用：实验设计、统计方法创新、论文写作、图像后期美化。真实 `/input/case.json`、`/input/task.md`、附件、字典和 `environment/resources.yaml` 才是事实依据；UCI 数据集名称不能代替现场读取。

## 输入输出与硬约束

- 工作区 `/app/work`；最终 `/app/output/result.json`、可编辑图件/代码/spec、源到图数据 CSV、独立图注、SVG、300 dpi 以上 PNG、manifest 与日志。
- 先保留原任务 `output_contract` **全部字段与嵌套结构**，再增量补充本 Skill 字段。
- 工具：`/skills/weekly-skill/scripts/visual_tool.py`；规格模板：`templates/figure_spec.json`。
- `schema_version`、`skill_version`、`spec_version`、`manifest_version` 当前均为 `2.0.0`。
- 每个正式图的 `figure-data.csv` 必须含源行号或聚合 `source_rows`；轴、单位、图例、误差定义、n、缺失排除、面板、导出规格必须机器可读。未要求的元素标 `not_checked`，不能留空后自称完整。

## 1. 画像、字段语义与统计口径

先读数据字典：宽表/长表、连续/分类/日期、主键、单位、缺失值、重复规则、样本量和分析目的。宽表多指标需分组长表时，先用真实分析代码转换并保存输入/输出哈希；不得在内存里隐式改口径。

在 `figure-spec.json` 明确：

- `where`：精确等值筛选；复杂筛选先固化派生 CSV。
- `drop_duplicates`：`true`（全字段）或主键列数组；只有字典依据才去重。
- `missing_values`：显式缺失集合；空串等常规缺失有默认值，`-999/-9999/9999` 若未声明会直接失败，避免被当真实值。
- `x/y/group`：列、标目、单位、类型；单位没有时用空串，不能不存在的字段硬画图。
- 统计假设需要检验时真执行并记录方法、统计量、自由度/p 值；未检查写 `coverage.statistics=not_checked/issues`，不能只给“显著”。误差线仅自动计算 **SD（样本标准差）或 SEM（均值标准误）**，每组至少 n=2。CI95 或其他区间必须来自实际统计计算并人工复核，不把 1.96×SEM 冒充小样本精确 CI。

IQR 异常值不自动删。箱线图直接显示 1.5×IQR 须与离群点；其他图若排除异常值，必须另有明确规则、前后行数和 `change_log`。

## 2. 图表选择可执行，不用面积/角度夸大差异

```bash
python3 /skills/weekly-skill/scripts/visual_tool.py recommend /app/output/figure-spec.json
```

`recommend` 检查真实字段类型与 `purpose`，输出 `recommended/reason/rejected/warnings/render_supported`：

| 数据结构与目的 | 图型 | 必须避免 |
|-|-|-|
| 连续 x + 连续 y，相关 | `scatter` | 用点面积表达未声明第三变量 |
| 有序日期/连续 x + 连续 y，趋势 | `line` | 时间序列改无序并列柱 |
| 无序分类 x + 连续 y，比较 | `bar` | 饼图角度、非零基线、无必要双轴 |
| 分组连续 y，分布 | `box`（类别放 x） | 只给均值隐藏分布与 n |
| 单连续变量，分布 | `hist` | 未记录 bin 规则/边界 |
| 构成 | 推荐 `stacked_bar`，但本版本 `render_supported=false` | 声称已自动渲染堆叠图；未实现就换可实现方案或标限制 |

类别超过 8 组停止硬塞单图，先依据任务分面/归并，不能用省略类别的“其他”静默丢数据。多面板分别渲染，使用 `requirements.panel=a/b/...` 并在 result 中给面板顺序；本工具输出单面板，不声称自动拼版。

## 3. 从真实 CSV 渲染，不是示例图

```bash
python3 /skills/weekly-skill/scripts/visual_tool.py render /app/output/figure-spec.json
```

支持 `bar/scatter/line/box/hist`，一次真实生成：

- `ID.svg`：可编辑矢量图，含 title/desc/viewBox；
- `ID.png`：真实 PNG 二进制、默认 85×60 mm、300 dpi（1004×709 px），含实际 pHYs；
- `ID-figure-data.csv`：每个散点/折线点的原始行号与坐标，或柱均值、SD/SEM/n/源行，或五数概况/离群点，或每个 bin 的边界/频数/源行；
- `ID-caption.txt`：可独立阅读的图注，自动带 x/y、n、缺失排除、误差定义、箱线统计口径、显著性证据（如有）；
- `ID-manifest.json`：完整 spec、源/产物哈希、坐标类型/范围/刻度、颜色/形状、质量记录、导出与未检项。

编码硬约束：柱与直方图数值基线为 0；`log_y` 只允许正值并在轴/manifest 明写 log10；`log_x` 必须先显式生成 log10 派生列，本工具不静默变换。颜色使用色盲友好候选，类别同时以形状或线型编码；默认细网格、最终尺寸字号至少 7 pt。图题与图例留白在分组图自动增加，仍以实际 PNG 目检为最后检查。

自动显著性只接受带 `x/label/p/method/evidence` 的真实结果；缺一项失败，**不计算或编造星号/p 值**。任务要求连续色标或空间比例尺时，本 CSV 工具拒绝伪造，标 `not_checked` 并使用实际空间数据/已提供工具。

### 字体与中文

PNG 使用内置 5×7 ASCII 字模直接栅格化，不依赖系统字体，输出为大写科学预览。中文/特殊符号默认保留在 SVG；若 PNG 出现未映射非 ASCII，`render` 返回 `issues+非零`，不静默以 `?` 冒充通过。为 PNG 提供 `x/y.label_png`，分类提供 `x.tick_labels_png`，标题提供 `title_png` 后可复审。SVG 文本仍需目标环境字体检查，manifest 明示 `svg_font_embedding=not_checked`，不得宣称已嵌入字体。

## 4. 独立图注与发表级交付

图注必须能脱离正文理解：研究变量与单位、分组含义、样本量、中心/离散指标、误差线的 SD/SEM 定义、显著性检验和精确 p（任务要求时）、缺失/异常处理、面板编号。不得只写“结果如图所示”。样本量、均值、SD、SEM 和分位数由源行计算，图注值与 figure-data 同步。

发表导出硬约束：PNG 实际 DPI≥300（不是改扩展名）；宽高 40–300 mm，推荐单栏 85 mm，最终字号≥7 pt，最多 4000 万像素防内存耗尽。SVG 保留编辑能力；其字体嵌入未自动通过。若固定期刊要求 CMYK、PDF/EPS、特定嵌入字体或连续色标，使用现场提供的真实导出工具补做并记录；本标准库工具不伪造 PDF/CMYK。

## 5. result.json 与全链审计

将 render 输出的 manifest 填入每个 `figures[]`，保留真实 `manifest_sha256/svg/png/figure_data/caption/source_sha256`。可复制工具与 spec 到 `/app/output` 保证独立复跑，并把实际命令写 `lineage.commands`。

```bash
python3 /skills/weekly-skill/scripts/visual_tool.py schema /app/output/result.json
python3 /skills/weekly-skill/scripts/visual_tool.py audit /app/output/result.json
```

`audit` 不只是文件存在性检查：

1. 校验 result/schema 版本、原合同增量字段、证据定位、覆盖状态与公平对照。
2. 验证源 CSV、figure-data、SVG、PNG、caption、manifest 哈希；检查 result 与 manifest 的路径、源版本、图注一致。
3. 从源 CSV 重算每条绘图记录和原始行映射，双向核对字段、值、行数、缺失排除与 n。
4. 用源数据与 spec **确定性重新绘制 SVG/PNG 并比较真实字节**；即使篡改图件后同步重填哈希，也会失败。
5. 检查轴类型/范围/刻度、单位、零基线、颜色+形状映射、近似色觉/灰度冲突、PNG 实际 DPI/像素、SVG title/desc/viewBox、图注 n/误差定义。

### result.json 增量模板（非正式答案）

```json
{
 "schema_version":"2.0.0","skill_version":"2.0.0","case_id":"","status":"pass|issues|partial|failed",
 "questions":[{"id":"Q1","answer":"","evidence":[{"artifact":"data.csv","location":"column/row/source_rows","quote":"逐字原文(文本结论)或省略","sha256":"64位hex"}]}],
 "figures":[{"id":"F1","manifest":"/app/output/F1-manifest.json","manifest_sha256":"64位hex","svg":"/app/output/F1.svg","png":"/app/output/F1.png","figure_data":"/app/output/F1-figure-data.csv","caption":"实际完整图注","source_sha256":"64位hex"}],
 "lineage":{"snapshot":"现场版本","tables":["data.csv"],"source_sha256":"64位hex","commands":["实际命令"],"plot_spec":"/app/output/figure-spec.json","code":"/app/output/visual_tool.py"},
 "coverage":{"cleaning":{"status":"pass"},"statistics":{"status":"pass|not_checked","reason":"任务未要求推断时"},"chart_selection":{"status":"pass"},"encoding":{"status":"pass"},"annotation":{"status":"pass"},"readability":{"status":"pass"},"export":{"status":"pass"}},
 "gain":{"protocol_version":"1.0.0","same_input":true,"same_permissions":true,
  "baseline":{"status":"measured|not_checked","quality":{"figure_correctness":null,"element_completeness":null,"readability":null},"efficiency":{"redraw_rounds":null,"manual_format_minutes":null},"evidence":[]},
  "skill":{"status":"measured|not_checked","quality":{"audit_passed":null},"efficiency":{"redraw_rounds":null},"evidence":[]},
  "quality_delta":null,"efficiency_delta":null},
 "unchecked":[],"sources":[{"path":"data.csv","sha256":"64位hex"}],"uncertainty":[],"change_log":[]
}
```

文本结论的证据必须有逐字 `quote` 和句/页定位；数据结论可用字段/行/source_rows 加 SHA256。`coverage` 七项均只能 `pass/issues/not_checked`，未检须给理由；`status=pass` 时 `unchecked/uncertainty` 必须为空。

## 6. 基础 Agent vs 本 Skill 对照

同一输入哈希、任务、权限、资源、字体、模型预算和种子运行两臂。逐图统计：视觉字段正确数/应核数、元素完整率、回源审计通过率、单栏缩放可读性、导出规格通过率；效率记录重画轮次、格式调整次数、人工核对条数与墙钟，并链接原生 trace。平台未提供基础臂时 `baseline.status=not_checked`、差不填估值；本仓变异 Bench 不算官方质量增益。

## 7. 异常处置表（识别信号 → 具体动作）

| 失败情形 | 识别信号 | 处置动作 |
|-|-|-|
| 缺失值/含缺失列 | manifest 排除源行；清洗后空集 | 报告排除行；全空停止出图；仅按显式 `missing_values` 排除，不把缺失当 0 |
| 异常值 | 箱线离群点/任务范围校验失败 | 默认保留显示；无规则不删；需排除时记录原值、源行、规则并 `issues` |
| 重复记录 | 主键重复且 spec 未声明去重 | 回字典判真实重复/重复测量；只有明确规则去重并报告前后 n，连接膨胀不得直接去重 |
| 样本量不足 | bar SD/SEM 组 n<2；推断假设不足 | 误差线失败并降级为无误差描述图（题面允许时）；统计推断标 `not_checked/issues`，不画假 CI/星号 |
| 类别过多 | >8 组 | 停止单图，按任务分面或显式归并后重跑；不静默省略类别 |
| 字段类型混杂/缺列 | 非缺失脏数值、日期解析或缺列错误 | 终止受影响图；按字典转换并留痕；仍然歧义则两种口径或交人工 |
| 宽表/长表不匹配 | 所需 x/y/group 不能一一对应 | 先真实 reshape 并保存派生表+血缘；不复制行凑长表 |
| 中文/特殊符号/字体缺失 | PNG `?` warnings、SVG 字体人工检查未通过 | PNG 未映射即失败；配置 `*_png` 后重渲染，SVG 字体补检；仍不可读标 `partial` |
| 导出失败/分辨率低 | 写入错误、PNG 解码失败、DPI<300、尺寸/像素不符 | 不交付该图；调合法尺寸重渲染并 `audit`；不使用纯改名文件 |
| 权限不足 | 读写 OSError | 不绕过权限；输出转至 `/app/output`、中间到 `/app/work`，输入不可读则 `partial/failed` |
| 轴/单位/图例/图值错误 | audit 轴、映射、记录或确定性重绘失败 | 撤回图件，修 spec/代码后全链重跑；不手改图或只补图注 |
| 显著性无法解释 | 缺 method/evidence 或 p 越界 | 拒绝标记；实际检验补齐后再绘，无法解释则移除标记并 `unchecked` |
| 比例尺/连续色标缺数据 | requirements.scale_bar/colorbar 被任务要求 | 当前工具停止；输入真实空间/连续编码数据并用已提供工具，缺口明确标 `not_checked` |

## 8. 自测与边界

```bash
python3 bench/bench_run.py
```

Bench 覆盖五种图的正向渲染与审计，以及错值、同步篡改 SVG/哈希、未声明哨兵、n 不足、类别过多、空集、低 DPI、显著性无证据、中文字体降级和契约变异。合成示例不是正式答案。精确通过数见 `REVISION.md`。

明确边界：单 CSV、单面板；自动误差仅 SD/SEM；不自动做统计推断/CI；无堆叠柱、双轴、连续色标、比例尺、SVG 字体嵌入和 PDF/CMYK 自动导出。任务点名这些能力时必须用现场工具补做并复核，或在 `coverage/unchecked` 说明，不能以本 Skill 已全覆盖作结。
