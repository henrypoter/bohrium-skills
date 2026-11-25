# METHOD：方法说明、适用范围与限制

## 方法学要点

1. **证据库结构化**：以「逐字 quote + locator」为锚点，论点/数据/条件/局限四元分离。quote 必须能通过 `evidence_lib.py` 的原文子串核验，从机制上阻断编造与转述失真（找得到、对得上）。
2. **论断切分**：一论断一事实谓词，使每条论断可被独立判定真假与充分性；常识/衔接句不强行配引用，避免虚假支撑。
3. **引用充分性核验（脚本化）**：full/partial 绑定，每条 binding 必填 scope + 非空 note（判定理由）；充分性四值不再只靠模型自述，由 `evidence_lib.py` 内容级复核——supported 必须含 full（E10），full 的 quote 逐字覆盖论断数值（E7），内容词覆盖不足出 warning（E8）。针对「引用了但并不真支撑」这一基础 Agent 高频失败。
4. **强度分级与措辞对齐（脚本化）**：A-D 四级（SKILL.md 第 4 节）配允许措辞表；E9 机检强度词-等级；新增的 `evidence_audit.py` 进一步要求证据层等级理由+设计/样本/独立重复/共识 basis，论断层 level/rationale/uncertainty，校验摘要/冲突封顶 C。只写等级字母不再视为可复核的强度标注（说得准）。
5. **写作-核验回路**：起草→机器核验（绑定闭合、quote 锚定、判定一致）→修订→复验，报告落盘，他人可重跑（复得现）。
6. **诚实优先**：先写 partial result.json 再增量改进；证据不足/冲突/元数据缺失全部显式标注，不静默通过。

## 失败类型表（供复用与推广）

| 失败类型 | 本 Skill 对策 |
|-|-|
| 编造文献或 DOI | 元数据只抄材料；quote 原文锚定（E5） |
| 引用真实但不支撑论断 | full/partial + 四值判定 + E10/E7/E8 内容级复核 |
| 数字对不上 / 转述失真 | E7 数值逐字锚定（full 绑定） |
| 弱证据强结论 | 等级-措辞对照表 + E9 + S6/S7/S8 强度理由与上限机检 |
| 仅摘要冒充全文 | availability + locator/caveat 双标摘要，S2/S3/S7 强制封顶 C |
| 隐藏冲突证据 | position 标正反方向；conflicted 双向绑定+差异/裁决分析；C4/C5 拦截隐藏 |
| 正文与矩阵脱节 | M1 manuscript↔matrix 双向核对（兼容 [C#]/[C#:E#]） |
| 编号冲突 | E12 证据/论断 id 唯一性硬检查 |
| 结果无法复核 | 论断编号 + 证据库 + 核验报告落盘 |

## 适用范围与限制

- 适用：材料固定的学术写作/改写/综述段落、需要引用溯源的结构化写作。
- 限制：不联网检索新文献（材料外文献一律不引入）；PDF 解析依赖运行时工具，失败时降级为「仅可读部分」并在 uncertainty 标注；强度分级是启发式口径，不替代专家评审。
- 维护：字段与分级口径以本版本模板为准；改口径需同步 SKILL.md、模板与脚本常量。

## 依赖

仅 Python 3 标准库（json/re/os/sys/subprocess/tempfile），无需安装；脚本路径相对 Skill 根目录。

## 验证与复跑

- 内容级核验夹具：`python3 tests/run_tests.py`（正向零误杀、11 种变异必命中、异常路径降级），报告见 `tests/test_report.md`；v2→v3 真实 bug（E9 误杀、M1 误报、编号冲突漏检）由夹具复现后修复。
- 使用增益对照：`python3 bench/bench_run.py`，口径与边界见 `bench/bench_report.md`。
- 强度/摘要/冲突：`python3 bench/evidence_audit_bench.py`（19/19：3 正向零误杀、14 变异按规则码必中，另有2项摘要正向/变异），报告格式见 `docs/data_formats.md` §5。
- 产物 schema 与维护细则：`docs/data_formats.md`；相对已有方案的能力矩阵：`docs/positioning.md`。
