# 实验方案设计领域总课题：运行手册

## 环境与快速开始

Python 3.8+ 标准库，无安装/网络依赖。正式输入 `/input/task.md`、`/input/case.json`，中间文件 `/app/work`，输出 `/app/output/result.json`。

```bash
S=/skills/weekly-skill/scripts/exp_tool.py
python3 "$S" route --task /input/task.md --case /input/case.json --out /app/work/routing.json
```

返回多个 route 时全部执行。保留 routing 原对象并嵌入结果的 `routing` 字段；无命中返回 1 和 unsupported，应停止请求澄清。具体触发词与分诊表见 `SKILL.md`。

## 路由到命令

| 路由 | 命令序列 |
|-|-|
| generation | `params`（有数值限值时）→ `audit → verify` |
| comparison | `compare comparison_input.json --out comparison.json` → 嵌入结果 → `audit → verify` |
| feasibility | `resources result.json`、`params result.json --spec limits.json` → `audit → verify` |
| parameter | `optimize problem.json --out optimization.json` → 嵌入结果 → `replay problem.json result.json` → `params` → `audit → verify` |
| interpretation | `interpret observations.json --out interpretation.json` → 嵌入结果 → `audit → verify` |

完整命令：

```text
route --task TASK --case CASE --out ROUTING
compare COMPARISON --out OUTPUT
resources RESULT
optimize PROBLEM --out OPTIMIZATION
replay PROBLEM RESULT_OR_OPTIMIZATION
interpret OBSERVATIONS --out OUTPUT
params RESULT --spec LIMITS
audit RESULT                    （check/schema 同义）
verify RESULT --source-root DIR
gain BASELINE SKILL --out OUTPUT
```

正常通过为0；科学/合同问题通常1；输入、JSON、路径、权限、NaN和网格预算错误为2。必须将实际问题写入结果，不得只看退出码写“成功”。

## 算法口径

- **比较**：硬min/max先过滤，min-max 按指标方向归一化，权重求 score；每指标 ±delta 做敏感性，同分按id。缺指标不一致不得计算。
- **资源**：设备材料四态+not_checked；成本分项乘法/求和；样本缺口；单步 max(设备,人工)+等待+周转，同并行组取最长，采购最长货期前置。
- **参数**：仅有限网格和显式线性模型；完整枚举，硬约束+三成本过滤，响应效用+Pareto，整对象 replay；不静默截断。
- **解释**：OLS intercept/slope/R²、逐点residual和MAD；阈值=max(声明阈值,2MAD)，严格大于才标异常；输出只作描述，不作因果。
- **证据**：文件 SHA-256、JSON Pointer 或文本逐字子串；PDF引文需要真实提取文本。
- **增益**：强绑定同 case/input/permissions；效率只取双方真实 telemetry，无基线 not_run。

## 合成最小示例（不是正式答案）

```bash
S=scripts/exp_tool.py
python3 "$S" route --task bench/fixtures/task.md --case bench/fixtures/example_input.json --out /tmp/routing.json
python3 "$S" compare bench/fixtures/comparison_input.json --out /tmp/comparison.json
python3 "$S" interpret bench/fixtures/observations.json --out /tmp/interpretation.json
python3 "$S" optimize bench/fixtures/problem.json --out /tmp/optimization.json
python3 "$S" audit bench/fixtures/good_result.json
python3 "$S" resources bench/fixtures/good_result.json
python3 "$S" verify bench/fixtures/good_result.json --source-root bench/fixtures
```

`good_result` 演示 generation 单路由；其他四路由的专属算法及动态失败由 bench 独立覆盖，正式混合任务必须嵌入所有对应产物。

## Bench 与限制

```bash
python3 bench/bench_run.py
```

当前 48/48。覆盖五类精确路由、混合/unsupported、比较硬拒绝/敏感性、线性和极端残差、资源算术、完整网格/replay、量程、证据引用、动态 schema 和公平对照。

规则路由不等于任意语义理解；OLS+MAD不等于机理；有限网格不覆盖连续高维；资源公式不覆盖复杂日历。遇到边界外任务须标注并转人工/专用工具。改动路由规则或算法时同步版本、文档、示例和 mutation bench。
