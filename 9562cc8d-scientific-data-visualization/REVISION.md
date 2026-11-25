# 修订说明：科研数据可视化 v2.0.0

## 完全纠正题域错配

旧目录为 `database-query-analysis`，本轮按题面完整重写为 `scientific-data-visualization`：删除 `scripts/data_tool.py` 和旧 SQL 模板，新增 `scripts/visual_tool.py`、`templates/figure_spec.json`；更新 `SKILL.md`、`REVISION.md`、`docs/README.md`、`bench/bench_run.py`、`bench/fixtures/good_result.json` 与 `GITHUB_URL.txt`。合成 CSV 保持原样。未改共享核心、未提交或 push。

## 实际效果（40）

- **闭环真出图**：`render` 从 CSV 生成五种图 `bar/scatter/line/box/hist` 的可编辑 SVG、真实 PNG、绘图数据、图注和 manifest，不是“建议画什么”的文本框架。PNG 由标准库 `zlib/struct` 编码，含真实 PNG signature、IHDR 和 pHYs，默认 85×60 mm、300 dpi、1004×709 px。
- **每个视觉数值对源数据**：散点/折线保留源行与坐标；柱状图从源行计算 mean/SD/SEM/n；箱线图计算 Q1/median/Q3、1.5×IQR 须和离群点；直方图保留 bin 边界、频数和源行。所有规则与去重/缺失/筛选显式化。
- **图件不是只靠哈希自证**：`audit` 先回源复算 figure-data，再按 spec 确定性重绘 SVG/PNG 并比较真实字节。本轮测试分别篡改 plot mean 和 SVG，并同步更新图件/manifest/result 哈希，仍被命中。
- **完整性硬门槛**：检查轴标目/刻度/单位、图例、颜色+形状、SD/SEM 定义、n、显著性证据、面板号、图注、导出格式/DPI/尺寸；比例尺、连续色标等未覆盖能力明确拒绝或 `not_checked`，不补造。
- **版本与可复跑定位**：result/spec/manifest 均为 v2.0.0；证据要求 `artifact/location + quote或sha256`，源/图/数据/图注/manifest 都有 SHA256，原行号/源行集合可定位，实际绘图命令、spec 和代码写入 lineage。

## 使用增益（25）

`gain` 要求同输入哈希、任务、权限、资源、字体、预算、种子的基础 Agent/Skill 两臂。质量指标逐项记录图值正确数、元素完整率、回源审计、单栏可读性和导出通过率；效率记录重画轮次、格式调整、人工核对和墙钟，并要求原生 trace。平台未给基础臂时 `not_checked`、差为 `null`，不把合成 Bench 写成官方增益。

相对基础 Agent 的主要增益是：图型选择有字段类型理由，统计口径直接进入图数据，交付前有机器阻止错误导出，而不是追求图型数量或代码行数。

## 创新增益（15）

1. **标准库双渲染器**：同一 scene 同时输出可编辑 SVG 和无外部字体依赖的 300 dpi PNG，具有真实尺寸、DPI 和无网络/第三方库复跑能力。
2. **视觉元素确定性对抗审计**：同时核对数值谱系和重绘字节，封堵“数字表通过但图被手改”“篡改后重填哈希”两类静默失败。
3. **图注自动从统计口径生成**：n、误差定义、缺失源行、箱线定义、显著性证据同步生成；显著性缺方法/证据直接拒绝。
4. **可读性双重编码与失败降级**：颜色+形状、近似色觉/灰度冲突检查、单栏尺寸/7pt 下限、类别>8 中止、中文 PNG 无映射非零退出。

边界：标准库 PNG 是 5×7 大写 ASCII 字模预览；SVG 文本保留中文但字体嵌入需外部检查。自动误差只覆盖 SD/SEM，不虚构 CI/p。连续色标、空间比例尺、堆叠柱、PDF/CMYK 和自动拼版不是本版本能力。

## 可靠体验（10）

异常表逐条覆盖缺失值、异常值、重复记录、样本量不足、类别过多、导出失败、字体缺失、权限不足，并补短表/宽表错配、混合类型/中文列名/日期、空结果、显著性无法解释、轴单位错误、比例尺/色标缺数据。每条有具体识别信号和停止、降级、重跑、标注或交人工动作。

实际 PNG 目检额外发现散点图题与图例重叠，已把分组图顶部留白从 16% 提高至 27%（更多图例行继续增加），并用修改后真实图确认可读；Bench 随后全量重跑，体现“机检 + 实图检查”而非只拼断言。

## 生态贡献（10）

保留 9 个文本资源，无图像/缓存混入提交：Skill、说明、修订、标准库工具、可执行 spec 模板、合成 CSV/JSON、Bench、GitHub URL。最小模板可通过一次 `render` 得到完整图件，静态 result 示例对未附真实图的环节诚实标 `issues/not_checked`。

## Bench 与实图证据

执行：

```bash
cd week4-road2-q2/submission
python3 -m py_compile scripts/visual_tool.py bench/bench_run.py
python3 bench/bench_run.py
```

最终结果：**40/40 PASS**。包括：推荐 7 项；五图真实 render + audit 10 项；柱值/图注/编码 3 项；抗篡改 2 项；异常及对数轴 7 项；中文降级与映射 2 项；静态/变异 schema 7 项；真实产物格式与版本定位 2 项。

另对实际 `F-bar.png` 和 `F-scatter.png` 读取目检：柱图零基线、SEM 和标目可见；散点图首轮标题/图例重叠，修复留白后再次目检通过。运行产物在临时 Bench 目录，不作为原题正式答案提交。

## 距仍需平台验证的部分

- 无官方固定 3 案例 × 3 重复、基础 Agent 对照、金标准、榜首分与原生 trace，故不能给出官方增益或“距榜首 X 分”。
- 当前标准库导出边界明确低于完整出版工具链：SVG 字体嵌入、PDF/EPS/CMYK、期刊特殊模板、连续色标/比例尺、复杂显著性括号与多面板需要现场资源补做或标未检。
- 近似色觉模型仅用于编码失败筛查，不声称临床级模拟；自动审计不能代替目标尺寸下全部视觉检查。
- GitHub URL 已从旧数据库目录改为本题路径；按要求未 push，未验证远端是否公开同步到 v2.0.0。
