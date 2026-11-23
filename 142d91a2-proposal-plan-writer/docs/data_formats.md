# 数据格式与复用说明（全部纯文本 UTF-8，无私有二进制）

## 1. meta.json（init 产出，工作区中间件）

```json
{"case_id": "来自 case.json 的 case_id/id，缺失则 unknown",
 "duration_months": 24,          // 正则抽取；材料未给为 null（check 记 gaps，不臆造）
 "budget": "30万元",              // 同上，可为 null
 "refs":   [{"id": "R1", "text": "材料原文行（逐字）", "source": "case.materials[0]"}],
 "priors": [{"id": "P1", "text": "前期基础原文行", "source": "case.materials[3]"}],
 "facts":  [{"source": "task.line1", "text": "含数字的事实行（≤60条）"}]}
```
refs/priors 的 `source` 是 case.json 内的 JSON 路径或 task.md 行号，可逐条回溯。

## 2. 编号约定（缺口↔研究内容映射的核心）

| 记号 | 出现位置 | 含义 |
|-|-|-|
| `缺口G1、G2…` | 综述/背景段尾 | 从材料收束出的缺口，逐一编号 |
| `RQ1（回应缺口G1）` | 研究问题章 | 每个 RQ 必须注明承接的缺口 |
| `内容一（对应 RQ1）` | 研究内容与方法 | RQ→内容块映射 |
| `[n]` / `[P#]` | 全文 | 引用第 n 篇材料文献 / 第 # 条前期基础清单 |
| `任务@RQ1:3:8` | gantt 入参 | 任务挂 RQ，起止月；非研究任务 `@公共` |
| `【材料缺口：…】` | 正文 + gaps | 材料不足双标注，禁止编造 |

check 据此做双向校验：每缺口被 RQ 承接、每 RQ 注明缺口、每 RQ 有内容块/成果/甘特任务、
每任务挂有效 RQ 或 @公共。孤儿缺口、孤儿 RQ、孤儿任务、越界引用均报 issue。

## 3. 甘特表格式（gantt 产出，嵌入进度章）

```
| 任务     | RQ | 起 | 止 |1|2|3|…|
|---|---|---|---|---|---|---|---|
| 模型开发 | RQ1 | 6 | 14 |.....#########...
```
列固定为 任务/RQ/起/止 + 按月刻度条（`#` 在轨 `.` 空档）。check 按 `| a | b | 起 | 止 |`
解析，止月 > meta.duration_months 即报越界。

## 4. check_report.json（check 产出）

```json
{"passed": true, "issues": ["…"], "gaps": ["材料文献仅2篇，难撑主题式综述"],
 "sections_present": {"背景": true, "…": true},
 "rqs": ["1", "2"], "n_refs": 3, "n_priors": 1,
 "matrix": {"RQ1": {"gaps": ["1"], "in_content": true, "in_outcome": true,
                     "tasks": ["数据构建", "模型开发"]}}}
```
`matrix` 即 RQ 闭环矩阵：缺口×内容×成果×任务四维，评分人可逐格复核。

## 5. notes.json（模型交付前手写，finalize 合并）

```json
{"status": "complete|partial|failed（缺省按 check 结果与 gaps 自动判定）",
 "sources": [{"claim": "关键论断/数字", "source": "R3/P1 或 case.materials[3]", "location": "1.背景"}],
 "uncertainty": ["无法确认事项"], "gaps": ["材料缺口"], "change_log": ["修改记录"]}
```

## 6. result.json（finalize 产出，契约全字段）

`case_id / status / deliverables{proposal_md,check_report,evidence_ledger} /
sections_present / sources[] / uncertainty[] / gaps[] / change_log[] /
checks{passed,issues,matrix}`。status 诚实：材料缺失→partial 并写明 gaps；运行失败→failed 写明原因。

## 7. evidence_ledger.md（finalize 自动产出）

三节：文献证据 [R#]（原文+来源路径）、前期基础 [P#]（清单为空时写明禁止虚构）、
论断-来源映射（claim ← source（location））。

## 复用方式

- 脚本零依赖（Python≥3.8 标准库），`python3 scripts/proposal_scaffold.py <init|gantt|check|finalize> -h` 查看参数。
- 模板/检查表：`templates/proposal_template.md`、`templates/checklist.md`（含评分锚点）。
- 自测题集：`tests/run_tests.py`（正向+变异+可靠 13 项）、`bench/bench_run.py`（确定性对照）。
- 上述格式均可被其他 Skill/脚本直接解析；编号约定与学科无关，迁移只需替换模板措辞。
