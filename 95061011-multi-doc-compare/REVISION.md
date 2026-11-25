# 修订说明（v4，对齐“对得齐 / 填得准 / 说得清 / 查得回”）

## 本轮新增，不替换既有矩阵流程

- **实际效果 / 可核验性**：`validate_and_render.py` 新增同文档段落归属与 quote 逐字命中硬检；跨文档借定位、引文不在所标段落均 exit 1。`index_corpus.py` 为每篇抽取文本记录 `content_sha256/content_bytes`，结果带 `schema_version/skill_version/run_id`、输入与输出摘要清单，复核者可以确认所查材料与产物版本。
- **可靠体验**：新增纯标准库命令 `python3 scripts/intake_audit.py audit --work W`，覆盖题面点名的主题不相关、同一论文多版本、图表不可读、结论矛盾且无法归因。它不是关键词分类器：Agent 必须给出主题/版本判断和同文档定位，脚本硬检排除边界是否被违反。
- **不可读图表**：`visual_gaps` 记 doc+figure_id+原因；若同一不可读图仍被抽成数值卡，硬错误。不会把“无法读取”解释成零值、阴性或未缺失。
- **无法归因冲突**：`unattributable` 必须永久保留 `resolution_status=unresolved`，`checked_dims` 覆盖 sample/method/condition/metric/unit；错误标成 resolved 或漏检查项会失败，result.uncertainty 自动留痕。
- **生态与复用**：新增 `bench/bench_intake_audit.py`，正向覆盖相关/不相关/图缺口/未解决冲突，变异覆盖漏分诊、越界引用、不可读图取样、伪解决冲突、跨文档定位、假引文；`case_meta` 和证据卡结构对其他论文集合可复用。

## 相对基础 Agent 的边界与价值

基础 Agent 可以做多篇摘要，但通常不能稳定执行“这篇是否越界”“这个不可读图有没有被取值”“无法归因是否被写成已解决”“这段引文是否真在所标论文”的确定性复核。本 Skill 把这些变成可执行硬约束和可交接清单。它**不**宣称自动理解论文主题、恢复不可读图、证明某归因在科学上正确，或替代平台的基础 Agent/Skill Agent 公平对照；所有未报告、不可读和未解决项仍明确降级。

## 验证记录

`python3 bench/bench_run.py`：**17/17**（原支持度 7 项 + 新硬闸 10 项）全绿；新增命令均有正向零误杀和变异必命中测试。该数字是本地确定性自检，不是官方评分、模型质量增益或榜首成绩。
