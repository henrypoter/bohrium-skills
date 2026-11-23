# 数据格式说明（全部 UTF-8 文本 / JSON，可直接复用）

## 1. sources.json —— 证据清单（步骤 0 产出）

```json
{"figures": ["图1","Fig. 2"],
 "tables": ["表1"],
 "values": [{"id":"S1","value":71.6,"unit":"%","desc":"处理组存活率","fig":"表1",
             "significant":true,"p":"0.003","disp":3.1,"disp_type":"SD",
             "test":"t","df":18,"stat":3.21}],
 "citations": [{"id":"C1","ref":"作者, 年, 期刊"}]}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| figures / tables | string[] | 是 | 材料中实际存在的图表编号（中文"图1/表1"或英文"Fig. 1/Table 1"均可） |
| values[].id | string | 是 | 来源标注 id，正文以 `[S#]` 引用；前缀不限 S（P1/D3 等均可，1–5 字母+数字） |
| values[].value | number | 是 | 材料原值，照抄不换算 |
| values[].unit | string | 否 | 单位原符号（支持 %、字母、μ ° / · ² ³） |
| values[].desc / fig | string | 建议 | 含义与出处（图/表/统计文件），供人工回溯 |
| values[].significant | true/false/null | 是 | true=有统计学显著证据；false=检验不显著；null=材料未给检验 |
| values[].p | string | 条件 | 有 p 值时记录；与 significant 矛盾会被 source_consistency 告警 |
| values[].disp / disp_type | number/string | 条件 | 均值后 ±离差（SD/SEM/CI），正文 ± 数据此溯源 |
| values[].test / df / stat | string/int/number | 条件 | t/z 检验三元组，记录后 statcheck 会重算核对 p（F/χ² 暂不重算） |
| citations[].id / ref | string | 否 | 文献标注 `[C#]` 与材料中的文献条目 |

## 2. report.json —— rd_check.py 核查报告（步骤 4 产出）

```json
{"summary": {"fail": 0, "warn": 0, "total_values": 6, "used_values": 6,
             "by_kind": {"number": 1},
             "by_score_dimension": {"结果正确性": {"fail": 0, "warn": 1, "info": 0}}},
 "items": [{"level": "fail|warn|info", "kind": "structure|discussion_block|purity|fig_ref|number|claim|statcheck|source_consistency",
            "loc": 12, "src": "S5", "msg": "..."}]}
```

- `loc` 为草稿行号，`src` 为来源 id（视条目类型而定），均可独立复核。
- `by_score_dimension` 把条目映射到评分维度（任务完成度/结果正确性/结果完整性/结果可核验性）；
  修复前后各跑一次，差值即质量增益证据，写入 result.json 的 change_log。
- 退出码：0=无 fail；1=有 fail；2=文件读入/参数错误。

## 3. 章节 draft.md —— 结构约定（templates/section_skeleton.md 为骨架）

- `## 结果` 与 `## 讨论` 用**独立标题**（合并成"结果与讨论"会触发 structure warn 并跳过纯净度/落位检查）。
- 正文每个数值后紧跟 `[S#]`，每条文献论断挂 `[C#]`，未确认内容写 `[待人工确认：原因]`。
- 结果段只陈述观察（无解释词、无文献引用）；讨论段四分块：主要发现复述 / 与文献对比 / 机制解释（推测须标注）/ 局限性（方法·样本·测量·统计四层）。

## 4. result.json —— 平台契约结果（/app/output/result.json）

必含：`case_id` + case.json output_contract 的**全部字段** + `status`（partial/complete/failed）
+ `sources`（正文物→S#/C#→材料出处的逐条映射）+ `uncertainty`（材料缺口/待确认项）
+ `change_log`（含核查前后 fail/warn 计数与修复记录）。示意骨架见 examples/minimal_example.md §3/§6。

## 5. bench_results.json —— 回归与对照结果（bench_run.py --write 产出）

`cases`（各夹具 exit/fail/warn/溯源率/断言）、`compare`（直写 vs 流程的 fail/warn、
错误检出数、spin 检出数、产物数）、`scale`（200 倍输入的判定与耗时）、`all_pass`/`failures`。

## 6. 检查清单（checklists/audit_checklist.md）

读得准 / 分得清 / 说得住 / 核得了 / 异常 五组逐条打勾项，每条对应一个机检项或 SKILL.md 规则，
可在任何结果与讨论写作任务中独立复用。
