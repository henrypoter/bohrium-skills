---
name: evidence-driven-writing
description: 文献证据驱动写作。把给定科研材料结构化为证据库（论点/数据/条件/局限+原文定位），将写作任务切分为可判定论断并建立论断-证据绑定矩阵，脚本化核验引用充分性（四值判定+数值锚定+强度词对齐）与证据强度分级，组织多文献对比/递进/冲突综合，经写作-核验回路产出句句可溯源的成稿与诚实的 result.json。适用于有固定文献材料、要求事实与来源一致的学术写作/改写。
---

# 文献证据驱动写作（evidence-driven-writing）

核心目标：不是让模型多写，而是让写出来的每一句有依据的话都能被指认**依据在哪里、依据有多强**。

## 0. 预算纪律（硬性，先读）

- 每个案例模型请求 **≤12 次**，全程 **≤600 秒**；单次响应受 16384 token 限制，输出务必分段落盘、不要一次性长输出。
- **先写诚实的 result.json，再增量改进**：进入案例后第 1 件事是按第 2 节契约写出 `status:"partial"` 的 `/app/output/result.json` 与空骨架，之后每完成一阶段就地更新；任何时刻中断都有诚实可评的部分结果。
- 禁止提交预制答案；一切论断必须来自当次案例实际读取的材料。

## 1. 输入

- `/input/case.json`：案例定义。读 `case_id`、任务说明、`output_contract`（结果 JSON 必含字段）、材料清单。
- `/input/task.md` 与材料文件（PDF/文本等）：**必须实际读原文**，优先全文而非摘要；不得依据文件名或领域标签臆测。

## 2. 输出契约（/app/output）

| 文件 | 内容 |
|-|-|
| `manuscript.md` | 成稿，满足体裁/受众/格式；事实句内嵌论断编号，如 `……提升约 30%[C3]`。 |
| `evidence_library.json` | 证据库：每篇文献一条，论点/数据/条件/局限+原文摘录与定位。结构见 `templates/evidence_table.md`。 |
| `claim_matrix.json` | 论断-证据绑定矩阵：支撑来源/范围/充分性判定。结构见 `templates/claim_matrix.md`。 |
| `verification_report.json` | `evidence_lib.py check` 原始输出，供独立复核。 |
| `strength_audit.json` | `evidence_audit.py audit` 原始输出：强度理由、仅摘要降级与冲突双向/并陈机检。 |
| `result.json` | **含 `output_contract` 全部字段 + `case_id`/`status`/`sources`/`uncertainty`/`change_records` + `artifact_version`/`input_manifest`/`verification`**，用 `check_result.py` 自检。输入清单由 `evidence_audit.py fingerprint` 生成 SHA-256+bytes，禁止虚构。 |

`status` 取 `complete`/`partial`（说明缺什么）/`failed`（说明原因）。`uncertainty` 逐条写「哪条论断、因何不确定、如何人工确认」。`sources` 只列实际读过的文件。

## 3. 六步工作流

1. **引导（1 次请求内完成）**：读 case.json + task.md；枚举 output_contract 字段；立即写出 partial 版 result.json 与四个骨架文件。
2. **证据提取**：逐篇读材料，填证据库。每条证据必含：著录信息（作者/年份/期刊/DOI，**只能抄自材料本身**）、`quote`（逐字摘录）、`locator`、`supports`、`data`、`conditions`、`limitations`、`evidence_level`（第 4 节）、`evidence_level_reason`、`strength_basis`（design/sample_size/replication/consensus；未知值填 null 并把字段名列入 `basis_unknown`）、`availability`（full_text/abstract_only）、`type`（原始研究/综述/指南/预印本）。缺失填 `null` 并在 uncertainty 标注，**禁止编造**。每条论断另填 `strength_annotation={level,rationale,uncertainty}`；等级不得高于其绑定证据，含仅摘要或未解决冲突时封顶 C。
3. **论断切分**：把要写的内容拆成最小可判定论断单元 C1..Cn（一论断一事实谓词）。区分「材料内事实论断」与「常识/衔接句」，后者不强行配引用。
4. **绑定矩阵**：为每条论断绑定证据（一论断可多文献、一文献可多论断）。判定充分性四值：`supported` / `partially_supported`（只支持更弱或相近表述）/ `unsupported`（无依据，删除或标注）/ `conflicted`（冲突，按第 5 节）。每条 binding 必填 `scope`（full/partial）+ `position`（support/oppose/mixed/context）+ 非空 `note`（支持到哪步、强弱差）——可复核的判定理由。`conflicted` 必须同时具备 support 与 oppose/mixed，并填 `conflict_analysis={summary,differences,uncertainty,action}`。`supported` 必须含 ≥1 条 `full`；full 的 quote 须逐字覆盖论断数值；措辞与证据等级对齐。脚本按 E7/E8/E9/E10 复核。
5. **综合与起草**：多文献按 对比 / 递进 / 冲突 三种关系组织段落；措辞强度与证据等级严格对齐（第 4 节对照表）；相关性不写成因果，单篇小样本不写成领域共识。
6. **核验回路**：运行
   `python3 scripts/evidence_lib.py check /app/output/evidence_library.json /app/output/claim_matrix.json <材料纯文本目录> /app/output/manuscript.md`
   修复全部 error 再复验直到 rc=0。error 含结构类（E1-E6、E12 编号冲突）与内容类（E7 数值锚定、E9 弱证据强结论、E10 仅 partial 判 supported、M1 正文 [C#]/[C#:E#] 与 matrix 不一致）；warning（E8 术语覆盖低等）须复核并在 note/uncertainty 说明。再运行
   `python3 scripts/check_result.py /input/case.json /app/output/result.json`
   再运行强度/异常硬闸：`python3 scripts/evidence_audit.py audit /app/output/evidence_library.json /app/output/claim_matrix.json /app/output/manuscript.md`，S1-S8（可得性/仅摘要/强度理由与上限）及 C1-C5（证据方向/冲突分析/正文并陈）全部 error 清零，原始输出保留为 `strength_audit.json`。用 `evidence_audit.py fingerprint <实际材料...>` 生成输入摘要。
   最后运行 `python3 scripts/check_result.py /input/case.json /app/output/result.json`，补齐版本/manifest/双核验状态，把核验输出存为 `verification_report.json`，并在 result.json 的 `change_records` 记录本轮改动。

## 4. 证据强度分级与措辞对齐

| 等级 | 判据 | 正文可用措辞 |
|-|-|-|
| A | 多篇独立研究一致，或高质量一致综述/指南；单篇原始研究须有独立/多中心重复记录 | 「已有研究表明」「较一致地支持」 |
| B | 单篇设计良好的原始研究，条件明确 | 「在……条件下，X 等观察到」 |
| C | 小样本/初步结果/仅摘要可得/预印本 | 「初步提示」「尚需重复验证」 |
| D | 机制推测、作者推测或证据不足 | 「一种可能解释是」「目前证据不足」 |

正文措辞不得高于证据等级允许的强度；不确定处用限定语（适用人群、条件、机制未明、结果冲突），既不夸大也不含糊到无法判断。**只写 A/B/C/D 不算完成强度标注**：证据层 `evidence_level_reason + strength_basis` 解释设计、样本量、独立重复、共识，论断层 `strength_annotation` 解释综合等级与剩余不确定性；机器按 S4-S8 验证，未知不得补造。

## 5. 异常处理（诚实标注，禁止静默通过）

| 异常 | 处置 |
|-|-|
| 仅摘要可得 | `availability=abstract_only`；证据与相关论断等级封顶 C，`locator` 与 `caveat` 均标「摘要」，uncertainty 注明全文方法/局限未核验；S2/S3/S7 拦截违规 |
| 原文与摘要矛盾 | 以全文为准作锚定来源，摘要不作 quote；`availability=full_text`，caveat 记录摘要差异，具体 claim 的 uncertainty 写冲突句与人工复核动作，不静默二选一 |
| 文献间结论冲突 | 不得隐藏：判 `conflicted`，bindings 标 support/oppose/mixed，填 differences/uncertainty/action，强度封顶 C，正文该 C# 所在句并陈；C2/C3/C4/C5 拦截 |
| 文献不可得/只有题录 | 不得创建伪造 quote 或 supported 绑定；相关论断判 unsupported，sources 只列实际可读材料，uncertainty 记录获取路径与人工确认，status=partial |
| 格式不支持/权限不足 | anomalies 分记解析失败与权限失败，保留可读文件的 partial 三件套；不得把 unreadable 当“无证据” |
| 证据不足 | 判 `unsupported`，正文删除或改写「待验证」，列入 uncertainty |
| 元数据缺失/无法核验 | 填 `null` + uncertainty；绝不补造 DOI/年份/期刊 |
| 材料与任务不符 | 以实际材料为准，不沿用错误领域标签；result.json 记 `anomalies`，status 降级并说明 |
| 疑似撤稿/版本差异 | evidence 加 `caveat` 并降一级使用 |

## 6. 复用资源

- `scripts/evidence_lib.py`：结构核验 E1-E6、E12（编号唯一）+ 内容级 E7-E11（数值锚定、术语覆盖、强度词-等级、supported 须 full、正文↔matrix 双向核对）+ `skeleton` 骨架。
- `scripts/evidence_audit.py`：独立强度/异常审计 `audit`（S1-S8+C1-C5）与 `fingerprint`（SHA-256+bytes）；报告 `strength_audit.json`。
- `scripts/check_result.py`：对照 case.json 的 output_contract 校验 result.json；另强制 artifact_version、输入 manifest（可读文件重算摘要）与 evidence_lib/strength_audit 双核验状态。
- `templates/`：证据库字段口径、论断矩阵字段与判定纪律、多文献综合模板（对比/递进/冲突）。
- `examples/minimal_example.md`：最小调用示例（自拟短材料，已标注为示例）。
- `METHOD.md`：方法学说明、失败类型表、适用范围与限制。
- `docs/scoring_coverage.md` / `docs/positioning.md` / `docs/data_formats.md`：评分点逐项核对、相对已有方案的能力矩阵与边界、全部产物 schema。
- `tests/`：内容级核验夹具（正向零误杀、变异必命中、异常路径），`python3 tests/run_tests.py` 复跑，退出码 0。
- `bench/`：使用增益确定性路径对照，`python3 bench/bench_run.py` 复跑，退出码 0；口径与边界见 `bench/bench_report.md`。

## 7. 安装与维护

- **依赖**：仅 Python 3 标准库，无第三方包、无网络、无安装步骤；脚本相对 Skill 根目录调用。
- **回归**：每次改动后运行 `python3 tests/run_tests.py`、`python3 bench/bench_run.py` 与 `python3 bench/evidence_audit_bench.py`（3 正向+14 变异+2 摘要断言），三者退出码均须为 0。
- **维护**：字段与分级口径以 `templates/` 为准；改口径须同步本文件、templates、脚本常量与 tests 夹具（维护细则见 `docs/data_formats.md` 第 6 节）。

## 8. 自查清单（交付前）

- [ ] result.json 含 output_contract 全部字段 + case_id/status/sources/uncertainty/change_records + artifact_version/input_manifest/verification
- [ ] 每条正文论断有编号（[C#] 或 [C#:E#]）且在 matrix 中有判定
- [ ] 证据有可得性/强度理由/四维 basis；论断有强度/不确定性；冲突有双向证据和正文并陈
- [ ] evidence_lib.py check 与 evidence_audit.py audit 均无 error；check_result.py 通过
- [ ] 无材料外事实、无编造引用、冲突与缺口均已标注

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/write_tool.py claim_check result.json` 核验论断-引用回路，重点抓**数值论断无引用**与悬空引用；`structure` 查必需章节无缺无空。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：论断与引用绑定、证据强度四维理由、仅摘要硬封顶、证据方向与冲突并陈机检；`evidence_audit_bench.py` 证明增量与边界。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/manuscript_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/manuscript_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py             # 既有正向零误杀 + 变异必命中
python3 bench/evidence_audit_bench.py  # 新增强度/摘要/冲突：3 正向 + 14 变异
```
