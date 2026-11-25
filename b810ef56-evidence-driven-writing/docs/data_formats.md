# 数据格式说明（schema）与证据台账样例

全部产物为 UTF-8 文本（JSON / Markdown），无私有二进制格式，第三方可直接读写复跑。
台账样例：`tests/fixtures/positive/`（最小合规样例）与 `bench/skill/`（含核验报告）。

## 1. evidence_library.json —— 证据库

顶层 `{"evidence": [Evidence, ...]}`；每条文献一个 Evidence 对象。

| 字段 | 类型 | 必填 | 含义与纪律 |
|-|-|-|-|
| id | string | 是 | `E1, E2, ...` 全库唯一（重复 → E12 error） |
| authors / year / title / venue / doi | string\|null | 是 | 只抄自材料；缺失填 null 并在 uncertainty 标注；year 四位、doi 须匹配 `10.\d{4,9}/...`（E1） |
| type | string | 是 | 原始研究 / 综述 / 指南 / 预印本 |
| availability | string | 是 | full_text / abstract_only；不可得材料不得伪造 Evidence |
| locator | string | 是 | quote 的章节/页/段；仅摘要可得填「摘要」且等级封顶 C |
| quote | string | 是 | 逐字原文摘录；E5 回材料纯文本做子串核验，编造必拒 |
| supports | string | 是 | 该文献真正支持的表述（不得比原文更强） |
| data / conditions / limitations | string | 建议 | 关键数字 / 适用条件 / 局限 |
| evidence_level | string | 是 | A/B/C/D（E6）；口径见 SKILL.md 第 4 节 |
| evidence_level_reason | string | 是 | 设计/样本/独立重复/共识形成等级的理由（S4） |
| strength_basis | object | 是 | design/sample_size/replication/consensus + basis_unknown；未知显式 null（S5） |
| caveat | string\|null | 否 | 撤稿/版本差异/仅摘要等警示 |

## 2. claim_matrix.json —— 论断-证据绑定矩阵

顶层 `{"claims": [Claim, ...]}`。

| 字段 | 类型 | 必填 | 含义与纪律 |
|-|-|-|-|
| id | string | 是 | `C1, C2, ...` 唯一（E12），与正文 `[C#]` / `[C#:E#]` 一致（M1） |
| text | string | 是 | 最小可判定论断（一论断一事实谓词），与成稿表述对应 |
| verdict | string | 是 | supported / partially_supported / unsupported / conflicted |
| strength_annotation | object | 是 | level/rationale/uncertainty；S6 必填，S7 校验不高于证据、摘要/冲突封顶 C |
| conflict_analysis | object\|null | 冲突时是 | summary/differences/uncertainty/action（C3） |
| bindings | Binding[] | 是 | supported ≥1 且须含 full（E3/E10）；conflicted ≥2（E4）且 support 与 oppose/mixed 双向；unsupported 不得含 full（E3） |

Binding 对象：

| 字段 | 类型 | 含义 |
|-|-|-|
| evidence_id | string | 指向证据库 id（必须存在，E2） |
| scope | string | full（完整覆盖论断）/ partial（只支持更弱或部分表述） |
| position | string | support/oppose/mixed/context（C1/C2/C4） |
| note | string | 判定理由：支持到哪一步、与论断强弱差（必填非空，E2） |

机检口径：full 绑定 quote 须逐字覆盖论断数值（E7）；内容词覆盖 <0.5 出 warning（E8）；
强词（证明/共识/导致/广泛接受…）所在论断的最强绑定须 A 级（E9 error），
软词（显著/明确/优于…）最强绑定 ≤C 出 warning。

## 3. result.json —— 案例结果（对照 case.json 的 output_contract 校验）

| 字段 | 必填 | 含义 |
|-|-|-|
| output_contract 声明的全部字段 | 是 | 如 manuscript / evidence_library / claim_matrix（R2） |
| case_id / status / sources / uncertainty | 是 | status ∈ complete/partial/failed；case_id 与案例一致（R3/R4） |
| change_records | 是（可空列表） | 修改记录：哪条论断因核验改过、怎么改 |
| artifact_version | 是 | 本次 Skill/产物规则版本，如 evidence-driven-writing-1.1.0 |
| input_manifest | 是 | {algorithm:"sha256",files:[{path,sha256,bytes}]}；用 `evidence_audit.py fingerprint` 生成，可读文件由 check_result 重算 |
| verification | 是 | evidence_lib 与 strength_audit 的 status/report，rule_version=evidence-audit-1.0.0；complete 时两者均须 pass |
| anomalies | 否 | 材料不符、格式不支持、权限不足等异常说明 |

uncertainty 元素建议 `{"claim_id", "reason", "action"}`：哪条论断、因何不确定、如何人工确认。

## 4. verification_report.json —— 核验报告（evidence_lib.py check 原始输出）

```json
{"summary": {"evidence": 2, "claims": 2, "supported": 2, "errors": 0, "warnings": 0},
 "errors": ["E7 C1: full 绑定 E1 quote 缺数值 ['98']（核对原文或降 partial）"],
 "warnings": ["E8 C2: E1 内容词覆盖 0.42<0.5，可能不支撑"],
 "notes": ["未提供材料纯文本目录：quote 锚定检查跳过（E5=unchecked）"]}
```

退出码 0=无 error / 1=有 error / 2=用法错误；报告写在 claim_matrix.json 同目录，可独立重跑。

## 5. strength_audit.json —— 强度与异常审计

复跑：`python3 scripts/evidence_audit.py audit evidence_library.json claim_matrix.json manuscript.md`。
S1-S8 检查可得性、仅摘要封顶/定位、强度理由、basis 完整性与等级上限；C1-C5 检查每条绑定方向、冲突双向、差异/不确定性/裁决路径及正文所在句并陈。退出码 0=无 error，1=有 error，2=用法/IO/JSON 错误。`fingerprint <材料...>` 仅输出真实文件的 SHA-256 和 bytes。

## 6. manuscript.md —— 成稿

Markdown，事实句内嵌论断编号 `[C#]` 或 `[C#:E#]`；措辞强度不超过证据等级允许
（SKILL.md 第 4 节对照表）；冲突并陈、证据不足处标「待验证」。

## 7. 安装与维护

- **依赖**：仅 Python 3 标准库（json/re/os/sys/subprocess/tempfile/time/copy），
  无第三方包、无网络、无安装步骤；平台加载 Skill 后脚本即可用。
- **路径**：脚本相对 Skill 根目录调用：`python3 scripts/evidence_lib.py ...`。
- **复跑**：`python3 tests/run_tests.py`（夹具回归）、`python3 bench/bench_run.py`
  （原对照基准）与 `python3 bench/evidence_audit_bench.py`（3 正向+14 变异+2 摘要断言）均应退出码 0；任一非 0 视为回归。
- **维护**：字段与分级口径以 `templates/` 为准；改口径须同步 SKILL.md、templates、
  脚本常量（LEVELS/VERDICTS/SCOPES/HARD_CLAIM/SOFT_CLAIM）与 tests 夹具；
  新增规则须配「正向不误杀 + 变异必命中」夹具各一。
