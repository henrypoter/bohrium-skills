# 数据格式与机检报告

## evidence_project.json

完整模板见 `templates/transfer_project.json`。顶层字段：

- `items[]`：证据最小单元。`id` 为字母+数字；`quote/source/strength/kind` 必填；`line` 或 `field` 至少一个；`kind=number` 时 `surfaces` 必填且每项必须是 quote 的逐字片段。
- `required`：关键结论、样本、指标口径、数值、单位、比较基准、方法、限定条件、图表和引用的保留开关。
- `strength`：`established/observed/preliminary/association/observational/not_significant/uncertain`。
- `conflict_group` + `resolutions`：冲突值组与人工 chosen；未裁决冲突是 fail。
- `terms[]`：canonical、aliases、abbreviation、expanded、plain。
- `changes[]`：每段 before_quote、draft_segment、action、reason、evidence_ids。

`source` 相对 project JSON 解析，也尝试 `/input` 和当前目录。PDF 需先实际提取为 UTF-8 文本，并在条目另记 original_file/page；脚本不会假装能解析 PDF。

## brief.json

`audience`、`genre`、`required_sections`、`min_chars/max_chars`、`target_channel`、`confidential/unpublished`、`handling`、`allowed_abbreviations`。公众稿的 audience 为 `public/公众/科普/lay/general` 时，白话解释和缩写展开是硬约束。

## evidence_report.json

`items[]` 含 `level/kind/msg/item/loc`；证据项附 `resolved_source` 与 `actual_lines`。主要 kind：`schema/source/verbatim/locator/surface/conflict/terminology`。退出码 0 只表示无 fail；bench 正向同时要求 warn=0。

## audit_report.json

主要 kind：

| kind | 判定 |
|---|---|
| retention / dangling_source / source_binding | 必保留项、来源 id、事实句来源闭合 |
| number / figure | 数字+单位逐字回所引证据，图表引用保留 |
| claim_strength | 相关≠因果、初步≠定论、不显著≠显著 |
| terminology / abbreviation / audience | 术语锁定、首次展开、公众白话解释 |
| genre / length | 指定小节和篇幅 |
| change_schema / change_anchor / change_coverage | 每段原位置、改后、理由和证据可复核 |
| disclosure | 涉密/未发表材料的不外传、人工审查和发布批准 |

`metrics` 给出去空白字符数、required/retained、source_tags、paragraphs、changes。

## result.json 与 gain

见 `templates/result_spec.md`。`result` 命令核对 output_contract、case_id、交付文件、complete 的 validation 闭环、A/B 协议和输入 SHA-256。`pending_platform` 不允许出现自行填写的 baseline；`local_fixture` 只用于随包回归，不能冒充平台对照。
