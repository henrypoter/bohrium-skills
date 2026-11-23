# 交付前自查清单（逐条打勾）

## 读得准
- [ ] 正文每个数值都能复制回 sources.json 某条记录（跑 rd_check.py，number 类 warn 清零或逐条解释）。
- [ ] 单位、有效数字、误差棒含义（SD/SEM/CI）与原材料一致；±离差已记录 disp/disp_type。
- [ ] p 值、检验方法照抄统计输出；t/z 已用 test/df/stat 记录，statcheck 项无 warn。

## 分得清
- [ ] 结果段无机制解释、无文献引用、无因果词（purity 项无 warn）。
- [ ] 讨论段四分块齐全：复述 / 文献对比 / 机制解释（标推测）/ 局限（discussion_block 无 warn）。
- [ ] 结果与讨论用独立标题，未合并成"结果与讨论"一节。
- [ ] 图表按编号顺序首次引用。

## 说得住
- [ ] "显著"仅用于 p<阈值 的比较且挂显著来源 [S#]；"趋势但未显著"有边界表述。
- [ ] 相关≠因果：观察性数据不出现"导致/证明"，机制推测带缓冲词（claim 项无 fail）。
- [ ] 获益/疗效类表述（spin）仅在统计证据支撑时使用。

## 核得了
- [ ] 正文图表编号与材料实际图表一一对应（fig_ref 无 fail）。
- [ ] 每条文献论断挂 [C#] 且能在材料参考文献中找到。
- [ ] 统计量三元组重算一致（statcheck 项无 warn）。
- [ ] sources.json 内 significant 与 p 无矛盾（source_consistency 无 warn）。
- [ ] result.json 含 output_contract 全部字段 + case_id + status + sources + uncertainty + change_log（含核查前后 fail/warn 差值）。
- [ ] 材料缺口、降调结论、[待人工确认] 项已全部写入 uncertainty。

## 异常
- [ ] 缺图/缺统计/单位不明/引用缺失均已按 SKILL.md 异常表处置，未编造。
- [ ] 若 status=partial，已写明具体限制与原因。
