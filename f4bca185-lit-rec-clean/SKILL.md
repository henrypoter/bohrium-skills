---
name: literature-data-cleaner
description: 清洗文献抽取记录并输出可统计表、行级变更与待确认清单。适用于给 CSV/TSV/JSON/JSONL 抽取表、单位/数字规则及行身份，要求统一字段、Decimal 单位与区间换算、同义词归一、按科学身份精确去重、异常处置和原始行/原论文追溯的任务；不是论断支持度判定或通用结论抽取工具。产出 /app/output/cleaned.csv、changes.jsonl、lineage.jsonl、review.json、result.json。
---

# 文献数据清洗与标准化

## 1. 任务边界与完成判据

输入是**实际抽取表 + 实际规则/身份 + 原论文定位材料**。原输入字节不可改；组织方制造的列名差异、重复抽取、缺值和未知单位都有身份，不能当作科学实验噪声，更不能跨条件/来源错并。字面换算不能替代科学冲突裁决。

只有同时满足下列条件才算完成：
1. `cleaned.csv` 可直接统计；每个声明字段有统一类型、缺失空值与允许值处理。
2. 每个数值转换真用 `Decimal` 计算，保留原值/原单位、目标单位、规则号、公式和精度。
3. 仅在**完整科学身份键相同且全部规范化值相同**时合并精确重复；不同 `experiment_id`、物质、条件、来源绝不自动合并。
4. 每条输出行沿 `_lineage_id → lineage.jsonl → source_refs/raw_records` 回到输入行；修改沿 `changes.jsonl` 回到规则号。
5. 未映射、未知单位、同义冲突、缺失/越界、身份不足、同身份不同值全部进入 `review.json`，不得静默填值或强并。
6. `audit` 退出码为 0；存在 pending 项时顶层只能是 `partial`，空表为 `failed`。

## 2. 运行纪律与输入识别

- 每案例建议 ≤10 次模型请求、≤600 秒；先读 `/input/task.md`、`/input/case.json` 和实际文件，不依据领域标签猜内容。
- 读完 `case.json` 后先把其 `output_contract` 的全部字段写成诚实 `status=partial` 骨架到 `/app/output/result.json`，记录 `case_id`；脚本完成后增量覆盖。任何时刻中断均保留部分产物。
- 找到实际 CSV/TSV/JSON/JSONL、规则文件、行身份及论文材料。不得假定必有 `claims-to-verify.json` 或 `target-fields.json`。
- 复制/生成规则到 `/app/work/rules.json`。根据实际表头配置 `fields`；根据**题面给定行身份**配置 `dedupe.identity_keys`。通常包含 paper/experiment/material/condition/metric，但不得机械照抄，字段必须真实存在。
- 原论文用于核对来源和冲突；若输入已有页/段/字段定位，将其作为字符串字段保留。找不到论文时标来源缺口，不捏造页码或引文。

## 3. 配置规则（唯一需要随案例修改的部分）

完整字段定义见 `templates/rules_guide.md`，可运行示例见 `examples/rules.json`：

```json
{
  "version": "case-specific-v1",
  "fields": {
    "experiment_id": {"type": "string", "aliases": ["Exp", "实验"], "required": true},
    "material": {"type": "string", "aliases": ["Sample"], "allowed": ["alpha"],
                  "synonyms": {"α": "alpha"}},
    "potential": {"type": "number", "aliases": ["E", "Potential"],
                   "target_unit": "mV", "decimal_places": 3,
                   "conversions": {"mV": {"factor": "1"}, "V": {"factor": "1000"}},
                   "min": -10000, "max": 10000, "rule_id": "R-E-001"}
  },
  "dedupe": {"identity_keys": ["experiment_id", "material"], "rule_id": "R-DEDUPE-001"}
}
```

- 换算统一定义 `target = original * factor + offset`，`factor/offset` 用字符串写可避免配置浮点误差；目标单位也须显式给恒等规则。`decimal_places` 只有规则要求时才设置，采用 ROUND_HALF_UP；否则不擅自舍入。
- 区间写 `1–2 mV` / `1..2 mV` / `1 to 2 mV`，输出主值 `low..high` 及 `__low/__high`；`1±0.1 mV` 输出中央值和 `__error`。反向区间、负误差不自动修复。
- 复合单位和数量级前缀必须逐条审核并列入 `conversions`，如 `g/L → mg/L` factor=1000；脚本不做未声明的量纲猜测。`unit_aliases` 只处理排版别名。
- 无单位但规则明确给出 `implied_unit` 时才可使用，并在 lineage 记录该规则；否则 `UNKNOWN_UNIT`。
- 规则优先级（不可颠倒）：**原始值/来源身份 > 字段映射冲突检查 > 同义词归一 > 数字解析 > 单位换算 > 允许值/越界检查 > 精确去重**。前面有冲突即停止该字段的自动处理，后一步不得覆盖科学冲突。

## 4. 标准闭环命令（纯标准库）

在 Skill 安装目录执行；Python ≥3.8，无第三方包、无网络：

```bash
python3 /skills/weekly-skill/scripts/literature_clean.py clean \
  --input /input/actual_records.csv \
  --rules /app/work/rules.json \
  --case /input/case.json \
  --out /app/output
python3 /skills/weekly-skill/scripts/literature_clean.py audit \
  --input /input/actual_records.csv --out /app/output
```

非 UTF-8 输入只有确认真实编码后才加 `--encoding gb18030`； delimiter 只有确认后才加 `--delimiter`。乱码时不试遍编码猜值。

产物：
- `cleaned.csv`：规范表，含 `_lineage_id`、`duplicate_count`、`_source_rows`。
- `changes.jsonl`：每次改值的 `rule_id/action/field/original/normalized/original_unit/target_unit/formula/source_ref`；精确合并另记判定键。
- `lineage.jsonl`：每行原始记录、所有来源行、字段规则与规范化签名；合并行保留全部 raw records。
- `review.json`：`id/type/signal/action/source_ref/field/status=pending`，是人工接管清单。
- `result.json`：保留 case 原 `output_contract` 字段，含 `case_id/status/records/sources/summary/uncertainty/change_records/gain/artifacts`。

**同一输入+同一规则重跑须字节一致。** Agent 最后还需检查原 `output_contract` 的字段语义并补齐任务特定字段；脚本为未知字段填 `null/[]` 只是诚实占位，不代表任务已完成。

## 5. 异常识别与动作（题面逐项）

| 情形 | 识别信号 | 具体动作 |
|-|-|-|
| 单位无法识别 | `UNKNOWN_UNIT` | 规范值留空，原值仍在 lineage；审核后增加 conversion 再重跑，不按字面猜换算 |
| 同义字段/同义值冲突 | `ALIAS_CONFLICT` / `NOT_ALLOWED` | 不投票、不选多数；列冲突原字段，回原文裁决 |
| 缺失 | `MISSING_VALUE` | CSV 保持空串；区分缺失与 0，列人工补证据位置 |
| 越界 | `OUT_OF_RANGE` | 不截断不删除；核对原值、单位与上下限，确认是真实极值还是抽取错 |
| 编码错乱 | `ENCODING_ERROR` / replacement chars | 停止该表；明确真实编码后重跑，不保存乱码猜测 |
| 空表 | `EMPTY_TABLE` | `status=failed`，不生成统计结论；检查表头/分隔符/材料是否缺 |
| 身份键不全 | `INSUFFICIENT_IDENTITY` | 禁止自动去重，保留行并请求补身份 |
| 同身份不同值 | `DUPLICATE_CONFLICT` | 全部保留并列 pending；这是潜在科学冲突，不做算术平均 |
| 数字/区间非法 | `INVALID_NUMBER` / `REVERSED_RANGE` / `NEGATIVE_ERROR` | 不猜值、不交换端点、不取绝对值，回原数字区域核对 |
| 未映射列 | `UNMAPPED_FIELD` | 不进入统计，raw record 仍保留；补 alias 或显式忽略 |
| 材料缺失/权限不足 | 文件不可读 | 保留部分结果，`status=partial/failed`，写缺哪个文件及人工接管路径 |
| 超时/预算不足 | 尚未 audit 或仍有 pending | 交付已落盘骨架和部分表，标 `partial`，不得声称闭环通过 |

## 6. 基础 Agent vs 本 Skill 的公平增益

`result.json.gain` 在平台未给基线实测时为 `baseline_not_provided`，**不得自造提升分**。若平台提供同输入、同模型、同权限、同预算的双方结果，按 `templates/gain_protocol.md` 先评分，再运行：

```bash
python3 /skills/weekly-skill/scripts/literature_clean.py gain \
  --baseline /app/work/baseline_metrics.json \
  --skill /app/work/skill_metrics.json \
  --out /app/work/gain.json
# 再用 clean --gain /app/work/gain.json 重跑，或把该对象原样并入 result.json 后 audit
```

质量主指标是预先定义的 `correct_cells/total_cells`，`false_merges` 独立计；效率用运行秒数和人工修正条数。输入哈希、权限、模型或预算不一致时 `gain` 硬失败，不计算不公平提升。

## 7. 最小示例、自查与维护

- `examples/minimal_example.md` + `minimal_input.csv` + `rules.json` 是合成接口示例，不是正式案例答案。
- 交付前在提交根目录跑 `python3 bench/bench_run.py`；当前 bench 覆盖 clean/audit/gain 的正向零误杀与变异必命中，须 **33/33 PASS**。
- 新增字段/单位时同步改规则版本、示例与变异 bench；不得为了消 review 而放宽身份键、允许值或单位约束。
- 限制：不 OCR、不自动判断科学冲突谁对、不做模糊实体合并、不凭领域知识补缺失。表格版式严重损坏时先人工修复并保留原文件哈希。
