# 工作表格式（worksheets.md）

三张表的列定义固定，可直接复制为 CSV 使用。列名不要改，便于他人复用与脚本校验。

## 1. 标注表 annotation.csv

```
record_id,title,year,source,annotator,decision,reason_code,evidence_snippet,evidence_location,confidence,note
R001,Example title,2021,PubMed,A,include,I1,"...object and outcome...",abstract p1,high,
R001,Example title,2021,PubMed,B,exclude,E2,"...only biomarker reported...",abstract p1,medium,
```

- `decision` ∈ {include, exclude, maybe}
- `reason_code` 必须来自 `reason_codes.md`
- `evidence_location` 写到页码/章节/表号，**不接受"摘要里"这种模糊定位**
- 每位标注者一行；同一 record 有 A、B 两行

## 2. 仲裁表 arbitration.csv

```
record_id,ann_a_decision,ann_b_decision,disagreement_type,arbiter,decision,rule_version,rationale,evidence_location
R001,include,exclude,decision,henry,include,v1.0,"摘要第2句报告了目标结局，B 的判断基于不完整摘要",abstract p1
```

- `disagreement_type` ∈ {decision, reason_code, evidence}
- `rationale` 必须写**为什么**，禁止只写"以 A 为准"
- 仲裁结论回写进 result.json 的 screening，并记入 change_log

## 3. 审计日志 audit_log.csv

```
step,input_n,output_n,operator,operation,timestamp,rule_version,note
search,0,312,agent,3 库检索,2026-11-20T10:00Z,v1.0,"Q1-Q3，库与字段见协议"
dedup,312,287,script,精确键+近似候选,2026-11-20T10:05Z,v1.0,"25 条精确重复，3 组近似候选待裁决"
screen_A,287,287,annotator_A,标题摘要筛选,2026-11-20T10:40Z,v1.0,"include 61 / exclude 214 / maybe 12"
screen_B,287,287,annotator_B,标题摘要筛选,2026-11-20T10:42Z,v1.0,"include 58 / exclude 217 / maybe 12"
arbitration,25,25,henry,冲突仲裁,2026-11-20T11:00Z,v1.0,"decision 分歧 19 条，reason_code 6 条"
final,287,287,henry,定稿,2026-11-20T11:10Z,v1.0,"include 62 / exclude 213 / maybe 12"
```

- `input_n`/`output_n` 必须能逐行首尾相接：上一行 output = 下一行 input（仲裁与定稿行除外时须在 note 说明）
- 与 `python3 scripts/search_tool.py audit result.json` 的结果对齐

## 4. 覆盖率/漏检表 coverage.csv（覆盖率类课题用）

```
ref_id,in_reference,retrieved,hit_status,miss_reason_code,miss_attribution,evidence
REF01,yes,no,miss,M1,"Q2 未覆盖同义词 'pyroptosis'",title match fail
```

- `miss_reason_code`：M1 查询词未覆盖同义表达；M2 检索字段过窄；M3 时间窗截断；M4 来源库未收录；M5 记录标识异常
- `miss_attribution` 必须指到**具体查询/字段/来源**，不能只写"数据库覆盖不足"
