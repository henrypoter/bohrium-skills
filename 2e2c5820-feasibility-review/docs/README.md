# 实验方案可行性评估：运行手册

## 依赖与安装

无安装步骤、无网络依赖、无第三方包；Python 3.8+，全部算法在 `scripts/exp_tool.py`。平台把本目录安装到 `/skills/weekly-skill`。输入是实际案例，输出写 `/app/output/result.json`。示例文件只用于开发自测，不能在正式案例中读取为答案。

## 一次完整审查

1. 读取 `/input/task.md`、`/input/case.json` 和所有清单/SOP/审批材料；逐方案版本建立 `sources`，记录实际 SHA-256。
2. 保留原 `output_contract` 字段，填七类检查、判断、风险和异常寄存器；缺项写 `not_checked`。
3. 从原材料生成 `/app/work/limits.json` 和只读源快照；生成规范化输入及权限清单的 SHA-256。
4. 按顺序运行：

```bash
S=/skills/weekly-skill/scripts/exp_tool.py
R=/app/output/result.json
python3 "$S" audit "$R"
python3 "$S" resources "$R"
python3 "$S" params "$R" --spec /app/work/limits.json
python3 "$S" verify "$R" --source-root /app/work/source_snapshot
```

5. 有基线时运行公平对照：

```bash
python3 "$S" gain /app/work/baseline_result.json "$R" --out /app/output/result_with_gain.json
```

`gain` 不是估分：覆盖数由 JSON 计算，效率只接受双方已有同口径 telemetry；无基线则 `gain.status=not_run`。

## 命令与退出码

| 命令 | 用途 | 通过 / 发现问题的退出码 |
|-|-|-|
| `audit RESULT` (`check/schema` 同义) | 七类、版本、证据、条件结论、十异常、gain | 0 / 1 |
| `resources RESULT` | 四态、样本、预算、关键路径和未决审批 | 0 / 1 |
| `params RESULT --spec LIMITS` | 量程交集、反推上下限、步进、单位、互斥 | 0 / 1 |
| `verify RESULT --source-root DIR` | 实际 SHA-256、JSON Pointer、逐字引文 | 0 / 1 |
| `gain BASE SKILL --out OUT` | 同输入/权限质量效率记录 | 0；不公平输入为 2 |

退出码 2 表示参数、权限、JSON、路径或非有限数错误，须按输出标 `failed/not_checked`，不能重述为科学不可行。

## 时间口径

- 单步：`max(设备占用,人工操作)+等待+检测周转`。
- 同并行组：最长单步；组间求和。
- 采购：所有 `purchase` 材料最长货期前置。
- 总工期：最长采购货期+各并行组之和。

资源预约合同如采用不同口径，应显式改输入结构并交专家复核，不能暗中套此公式。

## 最小示例（合成，不是正式案例）

```bash
python3 scripts/exp_tool.py audit bench/fixtures/good_result.json
python3 scripts/exp_tool.py resources bench/fixtures/good_result.json
python3 scripts/exp_tool.py params bench/fixtures/good_result.json --spec bench/fixtures/limits.json
python3 scripts/exp_tool.py verify bench/fixtures/good_result.json --source-root bench/fixtures
```

## Bench

```bash
python3 bench/bench_run.py
```

当前 33/33。每个新命令都有合规正向和强制失败变异； bench 只验证确定性行为，不代表官方案例成绩。

## 适用范围与维护

适用版本化文本/JSON 材料、有限数值限值、显式资源价格与预约合同。PDF 先用实际提取文本登记 `text_path`；复杂图片、非数值规格、连续优化、动态资源日历和法规判断交人工。维护版本：result/tool 3.0.0；改动判定口径时必须同步版本、示例和 mutation bench。
