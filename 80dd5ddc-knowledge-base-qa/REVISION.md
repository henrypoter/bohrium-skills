# 修订说明（v2 通用资料管理 → v3 证据问答；qa_tool 1.0.0）

## 实际效果（40）：把“答得有引用”改为逐论断可回链

- 新增 `index`：不只是字节盘点，还保存文件类型、权限、来源、完整 SHA-256、mtime、重复副本、显式 current/history，以及原文 `chunk_id + page/paragraph/start_line/end_line`。
- 新增 `search`：默认只检索 current canonical 文档，避免历史版本与重复副本混作当前独立证据；返回带版本和精确坐标的原文。历史问题才显式 `--include-history`。
- 新增 `qacheck`：逐 claim 核对 path、内容哈希、version/role、chunk、原文精确子串和页段行；索引被改、版本不符、引文拼接或坐标错误均失败。
- `scope` 固定 `index_sha256/searched_documents/excluded_documents/include_history`；索引外路径会被拒绝。`run` 固定工具版本、实际命令、输入根和起止时间。

## 使用增益（25）

搜索命中即返回完整引用骨架，减少“找到文件后再人工找段落、抄版本”的步骤；去重与版本过滤减少重复阅读；qacheck 一次列出错锚点、缺证和异常，减少返工。没有同输入基础 Agent 对照时，所有 gain 保持 null；本 bench 不冒充平台效率或质量增益。

## 创新增益（15）

1. **确定性证据索引**：`index_sha256` 对索引内容重算校验，复跑可比对；文本哈希、文件哈希和版本标签并存。
2. **版本感知召回**：同内容只留 canonical；同 base 不同内容才是版本候选；行政版本说明驱动 history 默认排除，未声明冲突不自动挑选 final/mtime。
3. **可机检缺证判据**：`no_evidence` 必须有 `missing` 和实际 search 命令；工具同时强调词面零命中不自动等于语义不存在，要求换词和范围检查。
4. **冲突证据结构**：`conflict` 必须至少两个不同锚点，分文件/版本呈现；resolved 必须有独立 resolution。
5. **异常与答案联动**：qacheck 要求每个 index anomaly 都在 result.exceptions 中交代；异常仍存在时不得写 resolved，修复后必须重跑 index。

## 可靠体验（10）

异常表已从通用文件管理改为本题点名的问答失败链：文件不可读/坏编码、扫描件无文本、PDF 未提取、权限不足、目录为空、空文件、版本冲突、证据互相矛盾，以及重复副本和索引变化。部分可检索时保留 `issues` 索引以回答已覆盖部分；完全不可检索时非零退出，不生成无依据事实。

PDF/DOCX 边界明确：标准库直接支持 UTF-8/HTML/DOCX XML；PDF 依赖实际可用工具产生带来源文本侧车，扫描件须真实 OCR。PDF 页码只来自 form feed，无法确认时为 null。

## 生态贡献（10）

`SKILL.md` 提供版本配置、检索命令、结果 schema、逐类异常恢复和最小示例；`docs/README.md` 提供独立复用说明；`bench/qa_bench.py` 可直接作为新金标准回归。原 file_tool 与其 bench 保留，不推倒已有字节清单能力。

## Bench 证据与边界

- `python3 bench/qa_bench.py`：**30/30 PASS**。正常库、PDF 页界、DOCX、精确引文和冲突并列零误杀；变异覆盖空目录、扫描无文本、坏编码、版本冲突、错哈希/版本/坐标/引文、缺证、范围造假、索引篡改、异常静默/假 resolved 和冲突单证据。
- `python3 bench/bench_run.py`：原回归 **10/10 PASS**。
- 全部是临时合成测试，不是平台固定三案例成绩。

相对基础 Agent 的边界：本 Skill 强在可复跑定位和防止无依据/错版本回答，不自动证明 claim 与 quote 的科学语义蕴含，不能替代复杂 PDF 解析、OCR、表格计算或独立实验校准。距榜首仍需平台案例验证：真实 9 文档库的别名与管理版本关系是否正确、扫描 PDF OCR 回链页码、跨段/跨文件综合论断覆盖率、实际搜索轮次与人工定位节省，以及三重复运行的稳定性。
