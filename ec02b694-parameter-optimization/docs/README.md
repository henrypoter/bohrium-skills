# 实验参数优化建议：运行手册

## 环境与数据

Python 3.8+ 标准库，无安装/网络依赖。读取实际案例和响应模型；`bench/fixtures` 全是标有 `example_only` 的合成示例，不得在正式运行当答案。输出 `/app/output/result.json`；中间 problem 和 optimization 放 `/app/work`。

## 最小调用

```bash
S=scripts/exp_tool.py
python3 "$S" optimize bench/fixtures/problem.json --out /tmp/optimization.json
python3 "$S" replay bench/fixtures/problem.json bench/fixtures/good_result.json
python3 "$S" params bench/fixtures/good_result.json --spec bench/fixtures/problem.json
python3 "$S" audit bench/fixtures/good_result.json
python3 "$S" verify bench/fixtures/good_result.json --source-root bench/fixtures
```

正式路径把 `S` 换为 `/skills/weekly-skill/scripts/exp_tool.py`，把 problem 放 `/app/work/problem.json`。优化对象须完整嵌入最终 `optimization` 字段，不能只贴推荐点。

## 命令

| 命令 | 机检内容 | 退出码 |
|-|-|-|
| `optimize PROBLEM --out OUT` | 有限域全枚举、硬约束、响应、三成本、Pareto、确定排序 | 0 有推荐；1 完整后无可行解；2 输入错误 |
| `replay PROBLEM RESULT` | 重算并比较完整 optimization 对象 | 0 一致；1 篡改；2 输入错误 |
| `params RESULT --spec PROBLEM/LIMITS` | 多源上下限交集、步进、单位、derived_min/max | 0 / 1 |
| `audit RESULT` (`check/schema` 同义) | 版本、响应、不确定度、搜索停止、成本一致、六异常、gain | 0 / 1 |
| `verify RESULT --source-root DIR` | 文件 SHA-256、JSON Pointer、逐字文本引文 | 0 / 1 |
| `gain BASE SKILL --out OUT` | 同 case/input/permissions 质量与真实 telemetry 效率 | 0；不公平输入为 2 |

## 算术约定

模型为 `intercept+Σcoefficient*parameter`。硬过滤先于效用评分；响应方向为 maximize/minimize，在可行集内 min-max 归一化，常数项 desirability=1。score 为正权重归一化和。Pareto 同时比较响应方向和时间/费用/样本最小化；同分时参数 canonical JSON 决定顺序，保证重跑一致。

预算成本模型必须来自实际合同/估算式，不得从当前最优值倒推预算。预算、响应阈值或权重改变必须提升 `problem_version` 并重跑。

## 基线对照

```bash
python3 scripts/exp_tool.py gain /app/work/baseline_result.json /app/output/result.json --out /app/output/result_with_gain.json
```

无基线保持 `gain.status=not_run`。运行时间、候选筛选返工和改参返工仅有双方同口径 telemetry 才填，重复实验分别记录。

## Bench

```bash
python3 bench/bench_run.py
```

当前 33/33。正向含完整枚举、可行推荐、完美重放、量程交集、真实引文和公平对照；变异含无可行解、超网格、NaN、min>max、预算裁剪、重放篡改、响应缺不确定度、错误停止、成本不一致、越界、错误步进、证据/权限不一致。

## 限制与维护

适用有限网格、显式线性模型/约束。连续、非线性、高维、随机或贝叶斯优化须声明不适用并转专用工具；不自动推断单位、因果效应、实时价格或安全阈值。任何 schema/算法口径变化需同步工具版本、SKILL、最小示例和 bench。
