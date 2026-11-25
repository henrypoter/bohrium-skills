# 最终迭代修订：文献数据清洗与标准化

## 任务纠偏

原目录是 `claim-evidence-verifier`（论断支持度/引文核验），与本题不符。本次将入口、模板、示例、bench 全部重写为抽取表清洗专用闭环，不再把“论断有引文”当作“数据清洗正确”。

## 按评分维度的实质改动

### 实际效果（40）

- 新增 `scripts/literature_clean.py clean`：实际读取 CSV/TSV/JSON/JSONL，完成字段映射、类型/允许值、缺失、同义词、Decimal 标量/区间/±误差、复合单位与前缀换算、越界检查、科学身份约束的精确去重。
- 输出可统计 `cleaned.csv`，同时产出 `changes.jsonl`、`lineage.jsonl`、`review.json` 与 `result.json`。
- 新增 `audit`：机检 CSV/JSON 一致、行级原值链、规则号、来源行、换算公式、精确合并判定键、pending 状态和输入 SHA256；有未决项不得 `success`。
- `--case` 保留原 `output_contract` 字段；未知字段只诚实占位，不伪造完成度。

### 使用增益（25）

- 新增 `gain` 与 `templates/gain_protocol.md`：固定同输入哈希、同模型、同权限、同预算，预先定义 `correct_cells/total_cells`、false_merges、runtime、manual_corrections。
- 平台未提供基础 Agent 实测时，结果明确为 `baseline_not_provided`，不编造提升；提供双方指标后才计算 delta。不公平输入或不可能指标会硬失败。

### 创新增益（15）

- 相对通用基础 Agent 的边界：可版本化规则及固定优先级、Decimal 真计算、区间端点转换、完整身份+全值签名的保守合并、合并后多原始行 lineage、规则/输入哈希可复跑。
- 科学冲突不由换算或多数投票裁决；身份不全禁止自动去重。脚本不会用模糊相似度跨实验/物质合并。
- 正向夹具证明等价单位/同义词可安全合并，变异夹具证明未知单位、身份不足、同身份异值等必被隔离。

### 可靠体验（10）

- SKILL 异常表逐项覆盖未知单位、同义冲突、缺失、越界、编码错乱、空表，并补身份不足、科学冲突、非法数字、未映射、材料缺失与超时。
- 失败动作不是“注意”：明确保持空值/保留全行/停止转码/补规则后重跑/人工接管位置。
- 同输入同规则重跑五类产物字节一致。

### 生态贡献（10）

- 新增 `templates/rules_guide.md`（字段字典、规则优先级、失效边界）、`templates/gain_protocol.md`、专用 result 模板。
- 新增可直接运行的合成 `examples/minimal_input.csv`、`examples/rules.json` 和最小示例文档。
- 单一纯标准库脚本，无网络、无第三方依赖；bench 可由他人替换规则与数据复用。

## 验证记录

`python3 bench/bench_run.py`：**33/33 PASS**。覆盖 clean/audit/gain 三个命令；正向零误杀，变异均命中，包含换算真值、区间、复合单位、不同实验零错并、科学冲突、来源哈希、断 lineage、无公式换算、不公平对照等。

## 尚未声称的能力/外部缺口

- 未运行组织方 3 个隐藏案例，未获得基础 Agent 白板或正式排名，故不声称质量提升百分比或榜首分数。
- 不 OCR、不自动裁断科学冲突、不做模糊实体合并；这些保留为人工确认。
- GitHub 附加分需公开仓库实际发布并匿名验证；本任务禁止提交/push，本次没有伪造新的公开链接或发布状态。
