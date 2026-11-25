# 修订说明（v2 → v3.0.0，2026-11-25）

## 逐条对齐“是否做对”与评分维度

- **逐字段明确规则和依据**：新增 `cleaning_tool.py plan`，从带版本的数据字典生成 `field_rules`；每项有 `field/rule/rationale/source`，测量、标识、分类角色分流，未检测/<LOD/录入缺失/真 0 不合并。全列缺失、未知语义和单位不明先阻断。
- **清洗结果直接支撑下游**：保留原值列、缺失标志、排除表与行级 `row_changes`；异常不自动盖帽/剔除，分类编码不求连续均值。跨表连接先过主键闸，避免样本量膨胀。
- **按记录复跑与逐字段核对**：新增 `plan / keys / convert / audit` 四道机检，加上原 `profile / recheck / schema`。`row_changes` 定位 CSV 行，转换写原值、新值、正逆公式，血缘写快照、规则/字典/工具/Python 版本、UTC 时间、随机种子与真实 SHA-256。
- **五类清洗与质量报告**：缺失/异常画像沿用成熟命令；近似重复升级为真实键审计；格式/编码与单位转换可逆；`audit` 强制 `result.quality_summary = quality_report = cleaned_table 实算`，不再只检查字段存在。

## 创新增益（15）：四个自评缺口均变为可执行能力

1. **字典推断字段策略**：`plan dictionary.json --csv data.csv` 输出字段级策略、来源定位与待确认问题。
2. **跨表主键对齐**：`keys LEFT RIGHT --left-key ... --right-key ...` 做 NFKC/空白/大小写匹配、未匹配键报告、规范化后重复与同键公共字段冲突检测，保留原键和两侧行号。
3. **可逆单位与编码转换**：`convert` 用 `Decimal` 逐行逆算验证；支持逐行混合单位、显式源编码到目标编码、原值列、转换日志、原子写入和输入输出哈希；未知单位、坏数值、量纲冲突不产出“成功文件”。
4. **报告与结果一致性自检**：`audit result.json --cleaned ... --report ...` 实算行数和字典令牌口径下的字段缺失数，并检查摘要/报告一致、规则来源、问题 evidence、版本和真实输入/产物哈希。

**相对基础 Agent 的边界**：基础 Agent 也能写通用清洗脚本；本版新增价值是上述四件事有固定机器接口、失败返回码和行级证据，不靠自然语言承诺。没有宣称这些自测等同平台对照增益。

## 可靠体验（10）与异常覆盖

SKILL 异常表覆盖题面全部点名项：空表、全列缺失、编码乱码/损坏、单位不明、主键冲突、缺失令牌混排、异常性质不明、文件权限不足/数据库连接失败、报告对不上。严格解码不再用 Latin-1 静默吞错；转换不覆盖原始输入；材料不完整时先交 `partial` 和 `unchecked`。

## 可核验字段与实际效果（40）

`result.json` 示例新增 `run`、`rule_trace`、`row_changes`、`quality_summary`、`conversion_audit`、`artifacts[]={path,sha256,type}`，并扩展 `lineage.inputs` 哈希。保留 `case_id/status/questions/aggregates/data_dictionary/gain/unchecked/sources/uncertainty/change_log` 和原案例 `output_contract`。说明明确 `recheck` 的能力边界：复杂筛选/转换还须代码及中间表，不能虚假扩大校验范围。

## Bench 证据（本地合成数据，不是平台成绩）

```text
python3 bench/bench_run.py
29/29 PASS
```

原有 10 项回归全保留；新增覆盖四个命令的正向零误杀，以及全列缺失、乱码、单位不明、主键/值冲突、未知单位、坏数值、行数/缺失数对账失败、版本/来源缺失、输入哈希造假等变异必命中。没有生成或提交正式案例答案/白板。

## 生态与剩余限制

更新 `SKILL.md`、`docs/README.md`、`templates/data_dictionary.md`，提供机器可读字典/转换计划/质量报告字段、最小调用和维护自测。当前 `convert` 自动处理 CSV 与文档列出的线性质量/体积/浓度单位，不覆盖任意专有格式；规则推断不替代领域确认，异常值处置仍需 workorder。平台固定三案例三次重复、基础 Agent 同预算原始对照和代码执行大图/全类型表格表现仍是榜首差距验证所必需的证据。
