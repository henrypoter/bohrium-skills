# 论文质量审查 Skill v3 使用说明

## 安装与依赖

无需安装第三方包；Python 3.8+ 标准库。提交目录即完整资源，入口为 `SKILL.md`，工具为 `scripts/review_tool.py`。PDF/图像解析使用实际运行环境列出的工具，脚本不会假装已经解析不存在的文件。

## 一次完整调用

```bash
# 先按 SKILL.md 从实际 case/PDF 得到 UTF-8 manuscript.txt
python3 scripts/review_tool.py index manuscript.txt --out index.json
python3 scripts/review_tool.py citations manuscript.txt --out citations.json
# Agent 按 templates/checklist.md 完成六分面语义审查并写 result.json
python3 scripts/review_tool.py verify result.json --source manuscript_text=manuscript.txt
python3 scripts/review_tool.py coverage result.json
python3 scripts/review_tool.py schema result.json
python3 bench/bench_run.py
```

所有 `--out` 命令将 JSON 写入指定路径；校验命令向 stdout 写一行 JSON。校验通过退出 0，审查不合法退出 1，用法/读取/JSON 错误退出 2。`citations` 的悬空引用是审查问题，因此退出 1；领域覆盖不能靠忽略退出码跳过。

## 命令能力与边界

| 命令 | 新增可机检能力 | 不能做/必须人工完成 |
|-|-|-|
| `index` | Unicode 偏移、页/行/段/句、section、源及句 SHA-256 | 扫描件 OCR、复杂版面语义；标题误识别须检查 |
| `verify` | quote 必须逐字，偏移/页/行/段/句/hash 全部回原文；多来源、重复条目 | 不判断语义真假；缺来源时直接失败而非跳过 |
| `citations` | 数字方括号、区间展开、参考文献映射、悬空定位、claim/source pair | 作者—年份、题录真实性、语义支持须另据真实来源 |
| `coverage` | 六类 checked/partial/not_applicable/not_checked 及范围/理由 | 不用 issue 数替代实际阅读 |
| `schema` | 契约 v2、工具 v3、证据/依据/缺失检索/可执行 fix/gain | 不代替 verify 的原文比对 |
| `compare` | 同 case/hash，独立逐条裁决后的质量与实际效率差值 | 无基线、无裁决时不能生成正式增益 |

## 输入/输出

输入：实际 `case.json`、`task.md`、稿件和允许的证据文件。输出：保留原始 output_contract 字段的 `result.json`，必须包含 `result_schema_version=2.0.0`、`tool_version=3.0.0`、case_id、版本哈希、issues、六分面 scope、gain、unchecked、sources、uncertainty、change_log。详细字段见 SKILL.md。

## 最小 synthetic 示例

```bash
python3 scripts/review_tool.py index bench/fixtures/sample_paper.txt --out /tmp/example-index.json
python3 scripts/review_tool.py verify bench/fixtures/good_result.json \
  --source manuscript_text=bench/fixtures/sample_paper.txt
python3 scripts/review_tool.py schema bench/fixtures/good_result.json
```

`good_result.json` 只演示一个“30 例无对照研究外推所有患者”的条目及六类处置，**不是正式案例结果**。其 quote 可逐字回查样本稿件。

## 基线对照文件

`decisions.json` 格式：

```json
{"case_id":"实际ID", "text_sha256":"实际文本哈希", "permissions":"两臂相同权限", "allowed_sources":"两臂相同资料范围", "budget":"两臂相同预算",
 "baseline":{"B1":"unsupported"}, "skill":{"P1":"supported"}}
```

baseline/skill 的 issue ID 必须全有裁决，`permissions/allowed_sources/budget` 均必填；每个结果还须有真实 `runtime.elapsed_seconds/manual_review_seconds/rounds`。若无平台对照，`gain.status=not_measured`，不要借用 bench 数值。

## 维护与限制

改规则须同步更新工具版本、REVISION、模板及变异 bench。本 Skill 不做语言润色、翻译、查重、排版或编辑决策；外部事实/被引全文不可读、图表不可读、篇幅未覆盖时必须显式降级。
