# 修订说明：systematic-review v2.0.0

基线为提交中原有 v1（仅有 `cite_check/theme_check/schema`，主要检查引用存在和主题覆盖）。本轮按任务包五个评分维度将流程机制化；`schema_version/skill_version/tool_version` 统一为 **2.0.0**。所有新增工具均为 Python 3 纯标准库，离线可执行。

## 1. 实际效果（40）

### 完成度与正确性

- `protocol_check`：把“标准先行”变成三项硬校验：完整检索式与检索元数据、标准数组规范化 SHA-256、每条 decision 的时间不早于 protocol。关键词串退化、事后偷改标准和空检索无动作会失败。
- `screen_check`：从 decisions 重算最终 included/excluded，而不相信手工填报。覆盖去重依据、题录/全文两轮、每次纳排的理由码/条款/逐字 evidence、protocol 版本、双人分歧裁决回链和六类计数。
- `quality_check`：纳入研究逐维评价均有原文定位；总分、归一化分数与等级按量表实际重算，评级必须影响具体 claims。
- `cite_check`：每个实质论断必须有纳入集内引用，且事实/推断/不确定显式分离；`location` 必须到页+段+句或结构化字段。
- `quote_check`：不仅检查 location 字符串，还重算原文件、抽取文本、quote 三类 SHA-256，并在锁定文本查找逐字片段。伪造 quote 后即使同步重算 quote 哈希仍失败。
- `theme_check` 已升级为后归纳校验：`derived_from` 必须等于该主题 claims 的实际引用文献集合，杜绝预设空主题和排除文献拼主题。
- `synthesis_check`：证据性研究空白必须有实际 query IDs、排除 records、这些 decisions 中真实出现的 reason codes、受影响 claims；冲突必须保留 direct/contradicts 两端。

### 完整性与可核验性

- `schema` 强制版本字段、case/task 哈希、run checkpoints、原 output_contract、计数恒等式、产物路径/哈希；未知效率指标允许 null，但必须同时给 `metric_notes` 的 not_checked 原因。
- 新增 `hash` 和 `--verify-artifacts`，使输入、原文、抽取文本和交付物可复跑定位。
- 空纳入集可以诚实降级：不多造 claims/themes，只能报告有边界的检索局限；pending、unchecked、undecided、failed 分别处理。
- `audit` 统一运行 10 个核心检查，任何一环失败均不能报告全绿。

## 2. 使用增益（25）

- `gain_check --update` 从同 case_id、同 case/task SHA-256、同 permissions 的双方原始结果重算质量与效率指标，避免手填比率；同时锁定 baseline 文件 SHA-256。
- gain 包含：论断引用覆盖率、可解析引用率、结构可核验引文率、筛选理由完整率、质量评价覆盖率、有证据空白率，以及耗时、模型请求数、人工返工项和差值。
- `examples/minimal/result.example.json` 的 gain 是**合成接口夹具**，不是基础 Agent 官方白板或真实竞赛成绩。该夹具中 Skill 相对合成 baseline 的引用覆盖率 +0.5、筛选理由完整率约 +0.142857、质量评价/有证据空白覆盖率各 +1、人工返工项 -3；同时耗时 +25 秒、请求数 +3，保留效率反向结果以避免编造“全面提速”。
- 正式案例没有可用基线时必须 `not_run/not_available + reason`；不得复制夹具值。`--allow-gain-not-run` 只豁免无基线这一外部条件，仍在 not_checked 留痕。

## 3. 创新增益（15）及相对基础 Agent 的边界

已实现题面点名的五类能力，并有可执行命令：

1. 检索式：结构化 concepts/synonyms/controlled terms，保留库/字段/布尔逻辑/时间/语言/run_at/intent/result_count（`protocol_check`）。
2. 纳排标准：criteria 版本、优先级、理由码及数组哈希，decision 逐条回链（`protocol_check + screen_check`）。
3. 筛选记录：两轮终判、判定人、双人分歧及裁决、去重簇、可重算纳入集（`screen_check`）。
4. 质量评价：逐维 evidence、量表版本、评级阈值、分数重算与结论影响（`quality_check`）。
5. 可复核综述：版本/计数/change_log/checkpoints、论断原文回链、冲突矩阵、证据性研究空白、同输入对照（`quote_check + synthesis_check + audit + gain_check`）。

**边界**：工具不能联网提供全局召回、不自动判断语义纳排、不评价引文语义是否足够支持、不代替领域质量判断、不自行解析 PDF。它把基础 Agent 较难稳定做到的“逐条留痕、版本一致、计算复核和失败阻断”固化下来；语义判断仍须 Agent 读原文，平台固定案例表现不能由 bench 代替。

## 4. 可靠体验（10）

- `SKILL.md` 与 `docs/EXCEPTIONS.md` 的异常表逐条覆盖题面七类：检索为空、数据库/接口超时、全文不可得、术语歧义、纳排条款冲突、纳入证据矛盾、权限不足。每项均给识别信号和实际降级/标注/人工动作。
- `exception_check` 自动抓空检索、query timeout、full_text=false 未登记，以及 pending+pass；超时/权限标记 resolved 必须有 retry evidence。
- 另覆盖重复、元数据缺失、上下文溢出、中断恢复。中断由 checkpoint 定位；数千条输入分批合并后重算。
- 非法 JSON、缺文件和输入类型错误输出结构化 runtime_input，不用 traceback 冒充正常结果。

## 5. 生态贡献（10）

- 复用模板：`protocol.md`、`screening_table.md`、`quality_scale.md`、`evidence_table.md`、`review.md`。
- 合成最小调用示例包括 case/task、4 条源记录、去重、双人裁决、Skill/合成 baseline、综述和证据表；明确不是正式答案或官方基准。
- `docs/README.md` 写安装、输入输出、12 个命令、路径规则、使用顺序、维护与限制；GitHub 地址保留在既有 `GITHUB_URL.txt`，链接公开性需发布前用未登录浏览器另验。

## 6. 验证结果

运行：

```bash
python3 bench/bench_run.py
python3 scripts/syn_tool.py audit examples/minimal/result.example.json \
  --baseline baseline.example.json --case examples/minimal/case.json --verify-artifacts
```

结果：**bench 68/68 全绿**；每命令均有合法正向与预期错误码变异，另覆盖 gain `--update`、无基线、空纳入集、未知效率指标、未知命令/非法 JSON/缺文件及 1200 记录/1200 论断单变异检测。合成示例总审计 **10/10 核心检查通过，errors=0，13/13 evidence spans 逐字验证**；唯一 not_checked 是仅一篇纳入研究所以研究间一致性不可判断，示例状态因此为 issues 而非 pass。

这些是合成机制验证，不是组织方 3 个固定案例上的成绩、真实基础 Agent 对照或榜首差距的实测。
