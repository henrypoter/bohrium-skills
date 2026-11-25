# 可复核系统性文献综述 Skill v2.0.0

## 1. 用途与边界

本作品把固定研究问题下的文献综述变成可重算流程：结构化问题、可执行检索式、标准预注册与版本锁定、去重、两轮筛选、双人分歧、质量评分重算、逐字引文回链、主题归纳、冲突/研究空白矩阵、异常处置及同输入基线对照。

**适用**：提供本批次文献/题录及检索条件，需要留下可审计纳入集与综合结论的任务。

**不适用/不声称**：全局文献召回、所有数据库实时检索、真实领域绝对新颖性、自动语义判定纳排、自动判断偏倚、替代学术审查。脚本机检“结构、计算、哈希、逐字是否出现”，Agent 必须另外核对语义是否支持论断。原文哈希证明版本一致，不证明出版元数据真实；元数据须按实际原论文或数据库记录核对。

## 2. 安装与依赖

- 无安装、无网络、无第三方依赖；Python 3 标准库。
- 提交最多包含 UTF-8 文本；运行产物可独立保留。
- 在 Skill 根目录运行下文命令，或把 `python3 scripts/syn_tool.py` 替换为 `python3 /skills/weekly-skill/scripts/syn_tool.py`。
- PDF 提取使用平台已有工具，并将 UTF-8 文本路径、提取器及版本写进 `records[].source`。本工具不会声称自行解析 PDF。

```bash
python3 scripts/syn_tool.py --version
python3 scripts/syn_tool.py hash /input/case.json /input/task.md
python3 bench/bench_run.py
```

所有机检 stdout 是 JSON，字段为 `ok/errors/warnings/not_checked/metrics/tool_version/schema_version`。退出码 0=通过、1=检测到错误、2=CLI 调用错误。`not_checked` 不会被静默消除；结果有未检查项时状态必须是 `issues/partial` 而不是 `pass`。

## 3. 命令与硬约束

| 命令 | 可机检硬约束 |
|-|-|
| `hash FILE...` | 实际文件字节及 SHA-256，不读取标签猜内容 |
| `schema RESULT [--case CASE] [--verify-artifacts]` | 版本、状态、原 output_contract、case/task 身份、哈希格式、计数恒等式、中断 checkpoint、产物哈希 |
| `protocol_check RESULT` | 研究问题结构化、布尔检索式、数据库/字段/时间/语言/运行日期/命中数、标准可操作性、标准数组哈希、判定不早于方案 |
| `screen_check RESULT` | 每篇纳排理由码+条款+逐字证据、标准版本、两轮终判、去重规范化依据、双人裁决回链、纳入集与六类计数完全重算 |
| `quality_check RESULT` | 纳入集覆盖、量表版本、全维度证据、分数/归一化/等级重算、影响论断回链 |
| `cite_check RESULT` | 论断分类、每论断引用、引用在原始清单且纳入集、双哈希、页段句或字段级定位、direct/partial/contradicts |
| `quote_check RESULT [--root DIR]` | 重算原文/抽取文本哈希；引文自身哈希；逐字串确实出现，允许仅空白差异 |
| `theme_check RESULT` | 每主题有带引用论断；`derived_from` 等于实际引用集合；无排除文献/未分类论断/预设空主题 |
| `synthesis_check RESULT` | 空白回链真实检索式；证据性空白必须有排除记录及实际理由码；冲突保留正反两端与论断影响 |
| `exception_check RESULT` | 异常类型/信号/动作/状态/影响对象/处置字段闭环；自动抓空检索、超时、全文缺失未处置及 pending+pass |
| `gain_check RESULT [--baseline FILE] [--update]` | case/task 哈希与权限一致；从原始双方结果重算质量/效率；基线文件哈希；篡改增益失败 |
| `audit RESULT ...` | 汇总上述 10 个核心检查；任何核心错误阻断“全绿”结论 |

相对路径默认相对 `result.json` 所在目录解析。例如 result 与 baseline 同在 `/app/output` 时写 `--baseline baseline-result.json`。`--root` 可指定材料包根目录。

## 4. 最小可运行示例（明确为合成接口夹具）

`examples/minimal/` 自带合成 case、task、4 条原始记录（含一个重复簇）、原文/抽取文本、双方结果、综述和证据矩阵。它不是组织方正式测试案例、白板、真实 Agent 基准成绩或预写答案。

```bash
cd examples/minimal
python3 ../../scripts/syn_tool.py audit result.example.json \
  --baseline baseline.example.json --case case.json --verify-artifacts
python3 ../../scripts/syn_tool.py gain_check result.example.json
```

该例展示：

- P1 标准先于 D1–D7；R2 的 D3/D4 分歧由 D5 回链裁决；R3 通过规范化 DOI 合并到 R1。
- R1 的质量总分、归一化及 moderate 等级可从维度映射重算。
- C1/C2 每个引文均通过原文、抽取文本、quote 三层哈希及逐字匹配；C2 明示推断边界。
- G1 由 Q1、R4、E-DESIGN 支撑，只声明合成语料边界，不声称真实领域不存在研究。
- 合成对照仅演示 gain 的计算和防篡改；示例 Skill 的耗时/请求数较大，同时人工返工项较少，说明效率不作单向虚构。

若需要演示 `--update`，先复制示例到临时目录，避免修改交付夹具。

## 5. 实际调用顺序

1. 读取实际 case/task/materials，保存原始 output_contract；建立 partial result 与 checkpoints。
2. 哈希输入、原文、抽取文本；登记缺失元数据和权限限制。
3. 填 `research_question/search/protocol/screening_criteria`，运行 `protocol_check` 后再判定。
4. 填 `duplicates/decisions/included/excluded/counts`，运行 `screen_check`。
5. 填质量量表与逐维评价，运行 `quality_check`。
6. 填 claims/themes/conflicts/gaps，运行 `cite_check + quote_check + theme_check + synthesis_check`。
7. 填异常和恢复记录，运行 `exception_check`。
8. 平台提供实际基线时 `gain_check --update`，否则 gain 标 `not_available + reason`。
9. 将综述与可编辑证据矩阵的实际路径和 SHA-256 写入 `artifacts`，运行完整 `audit`。

各表格定义见 `templates/`。`research_gaps`、`quality_appraisals`、`conflicts` 等详细对象结构直接参照合成 result，字段含义见 `SKILL.md`。

## 6. 可靠性与失败输出

七类题面点名异常的信号、降级/标注/人工动作见 `SKILL.md` 和 `EXCEPTIONS.md`。补充规则：

- 数千条记录分批筛选时保留批次 ID 和范围，最终合并 decisions 再重算，不虚称上下文覆盖。bench 包含 1200 记录/1200 论断结构检查及单变异检测，但这不是所有主题/数据库的性能保证。
- 任务中断：最后 completed checkpoint 之后继续；失败步骤必须 `failed`，最终 `status=failed/partial`，不能把未跑字段标 0。
- 空纳入集：允许 claims/themes 为空并进入 `not_checked`，只交付有边界的检索局限和空白；禁止用排除文献拼主题或综合结论。
- 材料缺失填 unknown；无法判断填 undecided/not_checked；运行失败标 failed。三者分别留证据。

## 7. 增益的可验证性与限制

对照使用相同输入哈希与权限。质量指标由原始 claims/citations/decisions/appraisals/gaps 重算，效率指标来自 run 实际记录，人工返工为日志中发现的返工项。没有平台提供的 baseline 就无法真实计算，保持 `not_run/not_available`，不得把示例值复制到正式 result。

`verifiable_quote_rate` 在 gain 中是结构指标；最终必须结合 `quote_check/audit` 的文件级逐字验证。耗时和请求数即使变差也应如实记录；不能为了达到“效率增益”删除较差指标。

## 8. 维护与自查

- 当前 schema/tool/skill：2.0.0。改动标准数组、命令输出结构或模板语义时同步升版本、更新 REVISION 和 bench。
- 新增每个命令必须至少一个合法正向、一个能触发预期错误码的变异；bench 运行到全绿。
- 自测只证明合成夹具上的工具行为，不代替组织方 3 个固定案例的实际效果或基础 Agent 对比。
- 发布前另需用未登录浏览器核实 `GITHUB_URL.txt` 实际公开可访问；本机检不验证 GitHub 链接。
