# 字段字典、转换与复算模板（v3）

以下均为**可编辑模板/合成示例**，不是组织方正式案例答案。实际 `unit/role/missing_tokens` 只能来自真实字典、QC 规则或 workorder；未知要留在 blocker/question。

## 1. 人类可读字段表

| 字段 | 含义 | role | 单位 | 编码/取值 | 缺失令牌 | 物理范围 | 来源定位 |
|-|-|-|-|-|-|-|-|
| sample_id | 样品编号 | identifier | — | 原始字符串 | 空串 | — | dictionary.fields.sample_id |
| concentration | 浓度 | measurement | mg/L | 连续 | 空串、-999、<LOD | [0,10000] | dictionary.fields.concentration |
| sex | 性别编码 | categorical | — | 1=男，2=女，9=未知 | 空串、9 | — | dictionary.fields.sex |

- 编码字段不要当连续变量求均值；“未知”编码不要当 9 参与计算。
- 缺失、未检测、<LOD、真值 0 分开标记/计数；聚合故障修复任务不自动插补。
- 数据库/Excel 转换 CSV 时保留表版本、工作表、导出 SQL、原始精度和行号映射。

## 2. `cleaning_tool.py plan` 机器字典

```json
{
  "dictionary_version": "dict-v1",
  "fields": {
    "sample_id": {"role": "identifier", "semantic": "样品编号", "missing_tokens": [""]},
    "concentration": {
      "role": "measurement", "semantic": "浓度", "unit": "mg/L", "target_unit": "μg/L",
      "physical_range": [0, 10000], "missing_tokens": ["", "-999", "<LOD"]
    },
    "sex": {
      "role": "categorical", "semantic": "性别编码", "missing_tokens": ["", "9"],
      "codes": {"1": "男", "2": "女", "9": "未知"}
    }
  }
}
```

命令：`python3 scripts/cleaning_tool.py plan dictionary.json --csv data.csv`。将输出 `field_rules` 转为 `result.rule_trace` 时补 `rule/rationale`，保留 `source`，不要仅复制自然语言总结。

## 3. 跨表键与聚合粒度

```bash
python3 scripts/cleaning_tool.py keys subjects.csv measurements.csv \
  --left-key subject_id --right-key subject_code > key_audit.json
```

键审计通过前不要连接。NFKC/大小写/空白归一仅用于匹配；原键及行号必须保留。1:N 关系先聚合 N 侧或 `COUNT(DISTINCT parent_id)`，子表行数不能冒充独立受试者数。

```sql
SELECT COUNT(*) AS joined_rows FROM a JOIN b ON a.id = b.a_id;
-- joined_rows 不应意外大于父表粒度；若大，先解释 1:N/重复键，而不是静默去重。
```

## 4. `convert` 转换计划

```json
{
  "plan_version": "convert-v1",
  "missing_tokens": ["", "-999"],
  "operations": [
    {"column": "concentration", "unit_column": "unit", "to_unit": "μg/L"}
  ]
}
```

固定单位可将 `unit_column` 换成 `from_unit:"mg/L"`。转换审计须保存每条 `row/field/original/converted/from_unit/to_unit/formula/inverse_formula/roundtrip_exact`，源文件不改名覆盖。没有单位证据时停止，不可从 1000 倍差异猜单位。

纯编码转换使用 `"operations":[]`，调用时显式 `--source-encoding gbk --output-encoding utf-8`。原始编码文件和 SHA-256 保留。

## 5. `quality_report.json` 骨架

```json
{
  "report_version": "qr-v1",
  "case_id": "实际case_id",
  "snapshot": "实际snapshot",
  "rows_before": 0,
  "rows_after": 0,
  "missing_by_field": {},
  "missing_tokens_by_field": {"concentration": ["", "-999", "<LOD"]},
  "duplicate_groups": 0,
  "outliers": 0,
  "conversion_count": 0
}
```

`result.quality_summary` 只复制 `rows_before/rows_after/missing_by_field/duplicate_groups/outliers/conversion_count`，两者必须一致。`rows_after` 和 `missing_by_field` 由 `audit` 从清洗表实算；零也如实写，不省略。

## 6. 行级变更与交付清单

每个 `row_changes[]`：`row_locator, field, original_value, action, new_value, rule_id, source`。剔除与修改分行记录，不能只写“已清洗”。

- [ ] `profile/plan` 完成；每个使用字段都有规则、理由、来源定位。
- [ ] 主键/未匹配/1:N 粒度已核对，排除规则有行号。
- [ ] 原值、转换正逆公式、编码与精度记录齐备，源文件未覆盖。
- [ ] `schema/recheck/audit` 全通过；复杂公式另有同快照代码和中间表。
- [ ] `run` 的实际版本/UTC/seed 与 `lineage` 快照/真实哈希完整。
- [ ] 缺失、异常、查询失败与人工确认分别列在质量报告和 `unchecked/uncertainty`。
- [ ] 报告数字、结果摘要和清洗表一致；修正前后值写 `change_log`。
