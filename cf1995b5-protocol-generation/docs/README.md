# 实验方案生成与优化

## 用途与边界
把研究目标落成可检验假设、可测变量、目标反推对照、可排期资源与风险替代路径。纯 Python 3 标准库；无需网络或第三方安装。工具不替代安全/伦理审批，不把规划合同当作真实采购、排期或实测效应。

## 输入与输出
读取实际 `/input/case.json`、`/input/task.md` 和材料；保留原 `output_contract` 全部字段，在 `/app/output/result.json` 增加控制需求、裁剪建议、异常和版本审计字段。合成接口示例见 `bench/fixtures/good_result.json`，不是正式案例答案。

## 命令
```bash
python3 scripts/exp_tool.py check result.json
python3 scripts/exp_tool.py controls result.json
python3 scripts/exp_tool.py optimize result.json --spec constraints-spec.json
python3 scripts/exp_tool.py params result.json --spec constraints-spec.json
python3 scripts/exp_tool.py schema result.json
```
退出码 0 表示对应检查通过，1 表示契约/科学字段/资源问题。`optimize` 输出设备量程与显式预算成本模型的参数交集、最小批次和异常处置，不直接改方案。spec 格式、成本模型限制、异常表和结果字段见 `SKILL.md`，工作表见 `templates/plan_spec.md`。

## 可核验字段
`case_id/input_id/plan_version/schema_version/source_version`、来源 `id/version/locator`、参数与判断 `source_locator`、结构化 `change_log`、`run_record.tool_version/commands`。预算、时间、设备、库存、货期与参数成本模型均须来自实际输入，不做无依据单位换算或线性成本假设。

## 自测
```bash
python3 bench/bench_run.py   # 当前 48/48
```
覆盖合规零误杀及风险五件套、变量测量、对照反推与映射、成本/时间算术、量程和预算参数裁剪、样本量批次、设备/档期/试剂/货期/缺输入和版本来源缺失变异。该结果不是平台得分或基础 Agent 对照增益。
