# 实验方案比较与选择

## 用途与边界
对给定候选做同口径矩阵、全成本/全周期核算、显式资源合同核验和可辩护选型。纯 Python 3 标准库；无需网络或第三方安装。只验证提交材料中的结构与合同，不把规划场景当作真实实验室、供应商状态或科学效果。

## 输入与输出
读取实际 `/input/case.json`、`/input/task.md` 和材料；保留原 `output_contract` 全部字段，在 `/app/output/result.json` 增加候选、选择、异常和版本审计字段。接口合成示例见 `bench/fixtures/good_result.json`，不是正式案例答案。

## 命令
```bash
python3 scripts/exp_tool.py schema result.json
python3 scripts/exp_tool.py compare result.json
python3 scripts/exp_tool.py feasibility result.json --spec feasibility-spec.json
# 选定方案正文可另跑：
python3 scripts/exp_tool.py check result.json
python3 scripts/exp_tool.py params result.json --spec feasibility-spec.json
```
退出码 0 表示对应检查通过，1 表示契约/科学字段/资源问题。真实异常未解决时保留非零报告和诚实状态，不修改输入合同求“全绿”。spec 格式、异常表和结果字段见 `SKILL.md`，工作表见 `templates/plan_spec.md`。

## 可核验字段
`case_id/input_id/plan_version/comparison_schema_version/source_version`、候选 `plan_version`、来源 `id/version/locator`、`change_log`、`run_record.tool_version/commands`。成本与时间分项必须有单位、来源且总和一致。

## 自测
```bash
python3 bench/bench_run.py   # 当前 44/44
```
覆盖合规零误杀及成本/时间算术、字段不齐、未知候选被选择、漏舍弃理由、无敏感性、全不可行恢复、设备/档期/耗材/预算/时间窗/参数冲突和版本来源缺失变异。该结果是本地功能证据，不是平台得分或基础 Agent 对照增益。
