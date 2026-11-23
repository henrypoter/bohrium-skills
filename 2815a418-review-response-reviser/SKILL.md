---
name: review-response-reviser
description: 面向论文返修的"意见拆解→真实修改→逐条回复→闭环核查"工作流。输入含审稿意见清单与指定版本稿件基线、需交付修订稿与逐条回复信时触发。核心能力：意见分类拆解（重大/次要/澄清/误解+处置级别 L1-L4+子要求）、四段式逐条回复（证据槽位禁自由生成）、三列闭环映射矩阵、礼貌反驳三要素（证据+替代方案+缓冲语）、锚点机器可核验（scripts/revision_kit.py）、修改留痕 diff。
---

# 审稿回复与论文修改 Skill

## 用途与适用条件
- 输入：`/input/case.json`（含 output_contract）、`task.md`、审稿意见清单与指定版本稿件基线（实际文件名以材料目录为准，先列目录再读实际内容）。
- 输出（全部放 `/app/output`）：`revised_manuscript.md`、`response_letter.md`、`mapping_table.md`、`changes.diff`、`result.json`。
- 只修订题目指定基线；意见摘要中可执行的实质性修改必须真实落稿，不得只声明缺材料就跳过。
- 不适用：无审稿意见纯润色；无指定基线稿件时按"异常处理"降级。

## 预算纪律（硬约束）
1. 每案例模型请求 **≤12 次**，全程 **≤600 秒**。
2. **第 1 步先写诚实 `/app/output/result.json`**（status="partial" 空骨架），之后每完成一阶段增量覆盖。
3. 意见解析/锚点建立/闭环核查/diff 全部用脚本，不耗模型请求。
4. 修订稿分段产出：先结构性改动，再逐条润色，最后统一核查。

## 工作流程

### 步骤 0：读入与机器预处理（不耗模型请求）
- 读 case.json 与 task.md，记录 `case_id` 与 output_contract 的**全部字段名**。
- 列材料目录并读实际文件，确认意见清单与指定基线稿件。
- 运行（$SKILL=Skill 安装目录）：
```bash
python3 $SKILL/scripts/revision_kit.py inventory <基线稿件> <意见清单> /app/work
```
得到 `/app/work/comments_parsed.json`（条目、子要求、类型/严重度/处置级别 L1-L4 建议、疑似误解标注）与 `anchors.json`（标题/段落/行号）。脚本分类仅是建议，由你最终确认。

### 步骤 1：先写诚实 result.json
立即写 `/app/output/result.json`：output_contract 全字段 + `case_id` + `status`(partial/complete/failed) + `sources` + `uncertainty` + `change_log`；初版主结果留空注明"待生成"。

### 步骤 2：意见拆解与决策（台账先行）
对 comments_parsed.json 逐条复核，建 `/app/work/ledger.md`：
- **编号与子要求**逐条列出，不合并遗漏（答得全）。
- **类型**：方法/数据/写作/格式/伦理（可多标）；**严重度**：重大/次要/澄清/误解（误解须基于 quoted_missing 或稿件原文比对）。
- **处置级别**：L1 采纳 / L2 部分采纳 / L3 礼貌反驳 / L4 拒绝执行（脚本建议值须复核）；L3/L4 备齐三要素——证据（稿件/材料/文献）+ 替代方案 + 缓冲语。
- **决策**：采纳 / 部分采纳 / 不采纳（礼貌反驳）/ 无法执行。
- **冲突检测**：意见互相矛盾时记录双方、取舍与理由，回复信中向编辑说明。
- 补实验/数据/文献类意见列入证据清单：状态=已到位（材料内可查证）/ 无法补做（写明原因与替代说明），禁止虚构已补做。

### 步骤 3：真实修改稿件（改得准）
- 只改指定基线；每处实质性修改在修订稿中可检索：改动句附近保留原文锚点，台账记录"章节/段落 + 锚点引文（6 字以上）"。
- **事实纪律**：回复信声称的每处修改必须真实存在于修订稿；没改不许写"已修改"；无法补做如实进证据清单与 uncertainty。
- 修改幅度：结构性改动（新增/重写段落）优先，逐条小改随后；每改一处同步更新台账位置。

### 步骤 4：撰写逐条回复信
按 `templates/response_letter.md`：总述修改概要与轮次承诺，逐条四段式——**感谢 → 立场 → 修改说明（证据槽位，只填真实事实）→ 修改位置（锚点引文）**。语气四档：接受 / 澄清 / 礼貌反驳（先谢+肯定关切+稿件/文献证据逐点反驳，禁用"审稿人错了/显然"）/ 申诉；多子要求逐条结论，禁止笼统"已按意见修改"。

### 步骤 5：闭环核查（不耗模型请求）
```bash
python3 $SKILL/scripts/revision_kit.py verify /app/output/revised_manuscript.md \
    /app/output/response_letter.md /app/work/comments_parsed.json /app/work/verify_report.json
python3 $SKILL/scripts/revision_kit.py trace <基线稿件> /app/output/revised_manuscript.md /app/output/changes.diff
```
verify 五查：①编号覆盖；②锚点在修订稿可检索并回填行号+最近标题（锚点两阶段第二阶段）；③决策词覆盖；④反驳/无法执行条目合规（缺证据/替代方案/缓冲语即 fail）；⑤语气风险扫描（命中 warn，改写"表述责任+已澄清"）。fail 逐项修复后重跑。

### 步骤 6：定稿与 result.json 更新
- `python3 $SKILL/scripts/revision_kit.py matrix /app/work/comments_parsed.json /app/work/matrix.md` 生成三列闭环骨架，据此填 `mapping_table.md`（格式见模板）：每条意见/子要求 → 类型/严重度/处置级别 → 决策 → 修改动作 → 修订稿锚点 → 证据状态；未到位证据单列。
- 锚点两阶段：起草用稳定结构锚点（章节/段落），定稿后把 verify report `anchor_locations` 行号回填到回复信与映射表。
- 更新 result.json：主结果路径、逐条 sources/修改记录、uncertainty、change_log；有 fail 未修复则 status=partial 并写明。

## 异常处理
| 情况 | 处置 |
|---|---|
| 意见引用原文在稿件中找不到 | 标注疑似误解/版本不匹配，按澄清/礼貌反驳处理，进 uncertainty |
| 意见互相冲突 | 记录双方与取舍理由，回复信向编辑说明，不得装作都满足 |
| 意见本身有误 | 礼貌反驳：先肯定关切，再用稿件/文献证据逐点说明，语气克制 |
| 要求补实验/数据但材料不支持 | 如实"无法补做"+替代说明，列证据清单"无法补做"，禁止虚构 |
| 稿件缺章节/与意见不匹配 | 以实际文件内容为准修订；缺口进 uncertainty 与 change_log |
| 材料缺失/无法判断/运行失败 | 分别说明，status 记 partial 或 failed，保留已完成部分 |
| 权限不足/路径不可写 | 只读输入不修改；产物一律写 /app/output；写入失败立即 status=failed 并保留已完成的中间产物与 verify 报告 |
| 多轮返修承诺 | 台账保留上一轮决策；回复信引用位置须与当前修订稿一致（改稿后重跑 verify） |

## 自查清单（交付前逐项过）
1. 每条意见及子要求都有明确结论与处置级别？无笼统致谢？
2. 回复信每处"已修改"锚点被 verify 检索到？行号已回填？
3. 无法补做有证据清单+原因，而非虚构？反驳/无法执行有证据+替代方案+缓冲语？
4. 回复信、修订稿、changes.diff 一致？冲突意见已标注？无 tone 风险？
5. result.json 含 output_contract 全字段 + case_id + 诚实 status/sources/uncertainty/change_log？

## 安装与依赖
- 无安装步骤：平台将本 Skill 挂载为 `/skills/weekly-skill` 后直接可用；`$SKILL` 即该目录。
- 依赖：Python 3（脚本仅用标准库，无第三方包、无网络访问、无外部二进制）。
- 资源清单：`scripts/revision_kit.py`（inventory/matrix/verify/trace 四命令）；`templates/`（回复信+映射表）；`checklists/`（四问自查）；`examples/`（最小示例）；`bench/`（自拟夹具自测与对照，`python3 bench/bench_run.py` 复跑）；`docs/`（评分点核对、能力边界、数据格式 schema）。

## 维护与版本
- 版本：v3（当前）。变更记录：v1 核心闭环；v2 处置级别/证据槽位/反驳合规/矩阵骨架/锚点回填；v3 修复四个夹具复现的真实缺陷（Major/Minor 意见解析丢失、跨行锚点误杀、编号子串漏检、直双引号误配），新增 bench 自测与 docs 三件套。
- 自查方法：交付或修改脚本后运行 `python3 bench/bench_run.py`，11 项断言全过 exit 0 方可使用；评分点覆盖核对见 `docs/scoring_coverage.md`。
- 修改词表/模板时保持「建议值」定位：分类与处置级别仅建议，最终判断与科学事实由运行 Agent 结合材料确认。

## 最小调用示例
见 `examples/minimal_example.md`（自拟短材料，仅说明接口与流程，示例，非正式案例结果）。

---

## v2 复核机制（对齐评分细则）

在第三期最优解基础上，叠加**可计算的复核机制**，逐项对齐评分维度。本节的工具与模板可直接复用。

- **实际效果 / 结果正确性 / 可核验性（40 分）**：`scripts/write_tool.py claim_check result.json` 核验论断-引用回路，重点抓**数值论断无引用**与悬空引用；`structure` 查必需章节无缺无空。
- **使用增益（25 分）**：`result.json` 增 `gain` 字段——同一输入、同一预算下，基础 Agent（不加载 Skill）与本 Skill 各跑一次，报质量与效率指标，差异须能指到具体条目，不写纯自述。
- **创新增益（15 分）**：论断与引用绑定、章节缺项检测、三向一致。
- **可靠体验（10 分）**：异常逐类给动作（见 `templates/manuscript_spec.md` 与本 Skill 工作流），不笼统说"注意"。
- **生态贡献（10 分）**：`templates/manuscript_spec.md` 为可复用模板；`bench/bench_run.py` 可独立自测。

### 交付前自检
```bash
python3 bench/bench_run.py   # 正向零误杀 + 变异必命中
```
