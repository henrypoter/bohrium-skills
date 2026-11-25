# Bench 报告（v4，科研成果转化专用）

复跑：`python3 bench/bench_run.py --write`。纯标准库，夹具运行时生成，均为自拟材料，不是正式案例或白板。

## 实测结论

**20/20，all_pass=true**；原始机器可读结果见 `bench_results.json`。

| 命令 | 正向零误杀 | 独立变异必命中 |
|---|---|---|
| `evidence` | 原文 quote、行号、surface、术语 schema 通过 | 引文改字→verbatim；错行→locator；未裁决冲突→conflict |
| `audit` | required、数字、术语、边界、逐段改动全通过 | 数字漂移、删必需项、因果/定论、别名、缩写未展开、缺体裁小节、无改动记录、before 不回原文、涉密公开缺审批、超篇幅 |
| `result` | output_contract、文件、闭环与合法 local_fixture gain 通过 | 缺契约字段→contract；A/B 哈希不同→gain；带 fail 冒充 complete→closure |
| 稳定性 | 额外 200 段保持零误杀且 <10 秒 | — |

## 同输入路径对照的边界

`deterministic_gain_fixture` 用同一输入 SHA-256 对比“模拟无核查错误稿”和“流程修复稿”的 fact_errors、manual_edit_items、rework_rounds，只证明规则能发现并定位问题。它不是基础 Agent 实跑，不用于声称平台质量得分。正式 result.gain 必须由平台 baseline 填充，否则只能 `pending_platform`。

## 已知覆盖边界

正向零误杀仅对随包夹具成立；词面规则不能保证所有学科的因果/不确定性表达都被识别。机检不做 OCR、DOI 联网验证、自动单位换算或科研结论真伪判断。
