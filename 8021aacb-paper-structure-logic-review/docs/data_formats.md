# 数据格式与安装维护（可复用资源说明）

全部格式为纯文本 JSON/Markdown，无私有二进制；脚本仅 Python 标准库。

## 1. 安装与维护

- **依赖**：Python ≥ 3.7，零第三方包；无网络访问、无环境变量、无写入技能目录外路径。
- **安装**：整目录复制即用；平台侧由评测器安装到 `/skills/weekly-skill`，本地验证可将 `submission/` 内容放任意目录后用绝对路径调用脚本。
- **自检**：`python3 scripts/result_check.py --selftest`；`python3 bench/fixture_test.py`（34 项）；`python3 bench/logic_bench.py`（20 项）；`python3 bench/path_compare.py`（双路径对照）。全部 exit 0 即健康。
- **维护**：词表（HEDGE/CAUSE/CORR/ARG/ZONE/SEC_KEYS，skeleton.py 顶部）与判据（references/checklist.md）为纯文本，可按学科扩展；改词表后必须重跑 fixture_test.py 确认「正向零误杀、变异必命中」不回退。版本记录在提交说明（SOLUTION.md）。

## 2. 锚点体系

`S<节号>` / `S<节号>.P<段号>` / `S<节号>.P<段号>.s<句号>`；节按标题切分（Markdown `#` 或数字编号），无标题稿整体为 `S1(UNTITLED)`、段即分组单元。锚点可用 skeleton.py 的切分函数复算（bench/path_compare.py 的 resolve() 为参考实现）。

## 3. skeleton.json（骨架图谱，脚本产物）

| 字段 | 含义 |
|-|-|
| input / total_chars / n_sections | 输入标识与规模 |
| sections[] | {sec_id,title,level,n_para,chars,paragraphs[]}；段落含 {id,chars,n_sent,zone,claim,evidence,hedge,cause,corr} |
| zone_stats | AZ 功能区域占比（goal/claim/evidence/method/result/contrast/background/conclusion/other） |
| missing_sections | 未识别出的学术节（abstract/introduction/method/results/conclusion/references） |
| redundancy_candidates[] | {pair,channel:shingle\|semantic_proxy,similarity,semantic,roles,position:echo\|cross,secs,arbitration,level:warning} |
| role_redundancy_candidates[] | 同论证角色跨节句对（须 LLM 仲裁） |
| boundary_candidates[] | {para,sec,reason}：强因果无限定 / 相关当因果 / 缺限制声明 |
| truncation_suspect / dup_scan_capped / warnings | 截断信号 / 扫描截顶标记 / 告警（含 empty_input、no_academic_structure） |

## 4. logic_audit.json（输入版本 + RQ/CB/截断候选）

由 `python3 scripts/logic_audit.py scan <稿件> -o logic_audit.json` 生成。`input_fingerprint` 含实际文件 path、SHA-256、bytes 与 anchors_version；`research_question_candidates[]` 含 RQ id、问题句锚点与四类章节建议锚点；`conclusion_boundary_candidates[]` 含 CB id、结论锚点、结论/结果数值差集、普遍化/因果提示与结果锚点；`truncation` 含 signals、last_anchor、last_text_sha256 和末文摘录。

候选不等于诊断。`logic_audit.py verify result.json logic_audit.json` 强制 result 对每个 RQ/CB 给唯一编号、真实锚点、范围关系与理由；closed/open/broader 还要相应闭环或 diagnosis。P=版本/摘要，Q=研究问题，B=边界，T=截断；任何 errors 均 exit 1。语义上是否真正回答科学问题、数据是否支撑结论仍由模型依据全文裁决。

## 5. result.json 诊断与留痕 schema（契约字段）

完整模板见 `references/result_schema.json`。关键条目：

```json
"artifact_version": "paper-structure-logic-review-1.1.0"
"input_manifest": {"algorithm":"sha256","path":"实际稿","sha256":"scan输出","bytes":0}
"logic_audit": {"rule_version":"logic-audit-1.0.0","audit_report":"/app/output/logic_audit.json",
  "research_questions":[],"conclusion_boundaries":[],"truncation":{}}
"diagnosis": [{"id":"D1","dimension":"六维之一","location":"S2.P3",
  "criterion":"判据+检索范围","evidence":"原文≤40字","type":"问题类型",
  "severity":"high|mid|low","action":"动作摘要"}]
"edit_plan": [{"id":"E1","action":"move|merge|split|narrow|add_transition|delete|rewrite_sentence",
  "level":"L1|L2|L3","anchor":"S2.P3","target":"S4.P1|null","detail":"操作","ref_diagnosis":"D1"}]
"change_log": [{"anchor":"S5.P1.s2","level":"L1|L2","original":"原句","revised":"新句",
  "reason":"理由","fact_note":"可选：有意改动解释"}]
"dimensions_checked": ["已逐维核查的六维列表；诊断无命中时必须填，用于区分无命中与未核查"]
```

约束：diagnosis 缺四元组任一项、change_log 出现 L3、事实 diff 漂移无 fact_note，均被 result_check.py 记 ADVICE；仅「result.json 不可解析 / 交付文件缺失」为 FAIL(exit 1)。

## 6. 交付物文件格式（优化稿留痕约定）

| 文件 | 格式约定 |
|-|-|
| diagnosis.md | 按六维分节；每条 `D# [维度][severity] 锚点 | 判据 | 证据 | 类型 | 建议动作` |
| edit_plan.md | 表格：E# / action / level / anchor / target / detail / ref_diagnosis；L3 行标注「只建议」 |
| revised_draft.md | 全稿文本，改动处行尾带留痕标记 `<!-- change:E# 锚点 -->`，未授权处保持原文 |
| skeleton.json | 见 §3 |
| logic_audit.json | 见 §4；scan 原始输出，不覆盖手工裁决 |
| result.json | 见 §5 |

## 7. 判据词表样例（criterion 字段写法，摘自 checklist.md）

| 维度 | criterion 样例 |
|-|-|
| research_question | 「贡献句 S1.P2.s2 在结果节检索 evidence 段=[] → 贡献无证据」 |
| section_structure | 「方法节占比 6%<10%（zone_stats），结论性内容 S2 先于证据 S5」 |
| argument_chain | 「S3.P1.s2 论断在全文检索 evidence 句=[无] → 论据缺失」 |
| paragraph_relation | 「S3.P2 与 S3.P3 主题跳跃且无过渡句」 |
| redundancy | 「与 S1.P1.s2 同贡献角色、shingle=1.0、非引言-结论呼应(echo)」 |
| conclusion_boundary | 「证据仅覆盖 3 个自建测试集(S3.P1)，结论表述为普遍因果」 |

## 8. 可复用清单

脚本（skeleton.py / result_check.py）、判据与动作词表（checklist.md）、契约模板（result_schema.json）、标注样例（examples/）、回归题集与对照（bench/fixtures + fixture_test.py + path_compare.py + bench_report.md）均可独立复用；二次开发只需遵守 §1 维护纪律。
