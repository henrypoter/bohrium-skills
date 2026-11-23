---
name: sci-figure-parse
description: 科研图表解析 Skill：对案例给定的 1 张原图及全部原表做可复核结构化解析。OCR 刻度定位 + 像素→数据标定；轴型双判据（R²+等距/等比预检）、残差审计剔除重拟合、双 y 轴强制 y_axis 归属；数值三档标注并指回原图。纯标准库脚本，判据外置 rules.json。
---

# sci-figure-parse：科研图表解析

把一张科研图（+原表）读成可复核的结构化数据，而不是一段像总结的文字。

## 0. 预算纪律

平台总预算 64 请求 / 900 秒，跑 3 案例 × 3 重复。**每案例 ≤12 次请求、≤600 秒**。

- **铁律：先写诚实 result.json 再增量改进。** 进案例先跑 P0（纯脚本、0 请求）落盘骨架；告急时带最诚实状态收尾（P4），宁可 partial 不可缺文件。批量数值交给脚本，不手抄数据点；不使用预制答案。

## 1. 输入约定

- 输入 `/input/case.json`、`/input/task.md` 及材料（v2 修订：必做对象 = **给定 1 张原图 + 全部原表**）。
- 工作目录 `/app/work`；产出 `/app/output/result.json`（output_contract 全字段 + `case_id` + `status`/`sources`/`uncertainty`），契约字段用 `init_result.py` 镜像。
- **缺口纪律**：只有图注未给像素的图列入 `uncertainty`（`caption_without_pixels`），不构造、不凭标签补数据。

## 2. 工作流（5 阶段）

### P0 探测与骨架（0 请求，纯脚本）
```bash
mkdir -p /app/work /app/output
python3 scripts/init_result.py --case /input/case.json --out /app/output/result.json
python3 scripts/probe.py /input/<图>           # 图像体检告警
python3 scripts/ocr_words.py /input/<图> > /app/work/ocr.json   # tesseract→词+像素框
```
PDF 先 `pdftoppm -r 300 -png in.pdf /app/work/page` 栅格化。

### P1 任务与图型识别（≤2 请求）
读 task.md/case.json：图表类型、子图划分、output_contract 要求。多子图时**每个子图一个 panel 键**，数值挂在 panel 下，杜绝跨子图错配。

### P2 坐标轴标定（≤3 请求）
1. `ocr.json` 的 `tick_candidates` 按质心聚类：x 轴 cy 接近在图下方；y 轴 cx 接近在图左；双 y 轴右侧另有一簇。
2. 写 spec（刻度像素↔数值对 ≥2/轴、unit、type=auto；格式见 axisfit.py 开头说明），运行：
```bash
python3 scripts/axisfit.py /app/work/spec.json --rules scripts/rules.json > /app/work/calib.json
```
3. 读 calib.json 判定（**判据外置 rules.json，可复跑可审计**）：
   - **轴型双判据**：`fit_quality` 比 R² + `spacing` 等距/等比一致性（对数轴 1,10,100 像素等距、比值相等）；冲突时 axisfit 写 `warnings`，须复查刻度词，不任选其一。
   - `dropped_ticks` 非空 = 剔除错读刻度并重拟合：重 OCR 确认；无法确认则保留审计记录并写入 uncertainty。
   - `verdict_confidence:"low"`（<3 刻度的对数判定）或 R² 低于阈值：复查像素与轴标签，必要时交 Agent 视觉裁决并在 sources 留痕。
   - 单位量级（mV vs V、×10³ 倍数）以 OCR 轴标题原文为准并与刻度数值交叉核对；拿不准记 `unit:"unknown"` 入 uncertainty，**不猜**。

### P3 数据还原（≤3 请求）
- 曲线：`trace.py 图 colors` 列主色簇 → `trace.py 图 extract --rgb R,G,B` 得像素折线；spec 加 `"trace_files"` 重跑 axisfit 得数据坐标序列。
- **双 y 轴强制归属**：panel 含 `y_right` 时，每个 point 必须写 `"y_axis":"left|right"`、每条 trace 名必须带 `@left`/`@right` 后缀；缺失时 axisfit 按 left 处理**并写 panel 级 warning**，绝不静默混轴。归属依据写入 sources，不足标 inferred。
- 点/柱/误差线：像素写入 spec `points`（`xerr_px`/`yerr_px` 给两端像素）→ 数据坐标 ± 区间；误差语义（SD/SEM/CI）图注明写=direct，否则 inferred。
- 显著性标记（*、**、n.s.）：记 annotation（panel、比较对、符号原文）；**不把星号当数据点**。
- 原表：CSV 直读；PDF/图片表用 pdftotext/OCR；表图互证不混替。比例尺：像素长÷标注长，写入 sources。

### P4 组装与校验（≤2 请求）
更新 result.json 全字段，写数据 CSV 到 /app/output；预装 matplotlib 时从 calib.json 重绘 `recon.svg`+`recon.png` 与原图对照核验（缺失则跳过），然后：
```bash
python3 scripts/init_result.py --finalize --case /input/case.json --out /app/output/result.json
```
打印 OK 方可结束；MISSING 项补齐或 `null`+uncertainty 说明。

## 3. result.json 契约与三档证据

骨架由 `init_result.py` 生成：`case_id`、`status`（success/partial/undeterminable/refused）、`status_reason`、`sources`（含 file/panel/region/basis）、`uncertainty` + output_contract 全字段。每个数值三档 `evidence`：`direct` 图中直接可读（刻度/标签/图注写明）；`inferred` 合理推断（标定换算、按图注规则推得），须带 `pixel` 与 R² 指回原图；`undetermined` 给原因不编数。

## 4. 异常处理（诚实降级，写入 status/uncertainty）

- 无坐标刻度 → 不标定；只给像素坐标+相对趋势，status=partial，axis 标 uncalibrated。
- 图被裁剪 → 可读部分照常解析；裁剪区的量标 undetermined 并说明。
- 图例缺失 → 系列以颜色/线型命名（series_rgb_210_40_40），uncertainty 注明
- 单位不明 → unit:"unknown"，禁止按常识补单位；列入 uncertainty
- 过曝/低对比 → probe 告警；降阈值重试 OCR，仍不行标 undetermined。
- 曲线重叠 → 只提取可分离段与端点，重叠区标 undetermined；不强行拆分。
- OCR 缺失 → probe 头解析仍给尺寸；靠可见信息定位刻度，降 partial。
- PIL 缺失 → trace 拒绝运行并说明；退化为 OCR 刻度 + 关键点人工读数。

## 5. 最小调用示例

见 `examples/minimal-example.md`（自拟合成材料，输出标注"示例"）：全链路及变异自检。

## 6. 依赖与限制

- 仅用 Python 标准库；PIL、tesseract、poppler、matplotlib 为预装可选增强，缺失按 §4 降级，**不 pip 安装**。
- 脚本：`probe.py`（图像体检）、`ocr_words.py`（OCR 词+像素框）、`axisfit.py`（标定/判别/数字化，阈值在 `rules.json`）、`trace.py`（取色描线）、`init_result.py`（骨架与校验）。
- 限制：不做无标尺显微图绝对尺寸；不凭图像鉴定物质；对数轴非正刻度无法拟合时明示。脚本均自包含单文件，可直接复制复用。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/read_tool.py support_check answers.json --text source.txt` 把每条证据引文在原文里做逐字匹配，不在原文的（误报）直接揪出；支持度分档统计。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：证据逐字回链、支持度分档。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/support_rubric.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/support_rubric.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
