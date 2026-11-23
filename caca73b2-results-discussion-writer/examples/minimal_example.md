# 最小调用示例（示例：材料为自拟短材料，非正式案例）

## 1. 示例输入材料（自拟）
表1：对照组与处理组的细胞存活率（%，n=5，误差棒为 SD）：
对照组 98.2±1.5；处理组 71.6±3.1（t 检验 p=0.003）。图1：两组柱状图。
任务：写结果与讨论小节。

## 2. 建立证据清单 sources.json（/app/work/sources.json）
```json
{"figures": ["图1"], "tables": ["表1"],
 "values": [
  {"id":"S1","value":98.2,"unit":"%","desc":"对照组存活率","fig":"表1",
   "significant":null,"disp":1.5,"disp_type":"SD"},
  {"id":"S2","value":71.6,"unit":"%","desc":"处理组存活率","fig":"表1",
   "significant":true,"p":"0.003","disp":3.1,"disp_type":"SD"},
  {"id":"S3","value":0.003,"desc":"组间t检验p值","fig":"表1","significant":true},
  {"id":"S4","value":5,"desc":"每组样本量","fig":"表1","significant":null}],
 "citations": []}
```
注：均值后的 ± 离差记 disp/disp_type；n 也记一条；有 t/z 统计量时再补
`"test":"t","df":28,"stat":2.5`，脚本按 statcheck 思路重算核对 p。

## 3. 先写诚实 result.json（骨架，status=partial，后续增量覆盖）
```json
{"case_id":"示例-demo-001","status":"partial",
 "manuscript":"","sources_map":[],"uncertainty":["材料无参考文献，文献对比块留空"],
 "change_log":["初始化骨架"]}
```
正式运行时须先读 /input/case.json，把其 output_contract 的全部字段原样纳入本文件。

## 4. 起草 draft.md（数值后挂来源标注，结果/讨论用独立标题）
```markdown
## 结果
处理组细胞存活率为 71.6%±3.1% [S2]，显著低于对照组的 98.2%±1.5% [S1]
（t 检验，p=0.003 [S3]）（图1，表1）。

## 讨论
### 主要发现复述
处理显著降低了细胞存活率 [S2]（p=0.003）。
### 与文献对比
[待人工确认：材料未提供参考文献]
### 机制解释（推测须标注）
存活率下降提示处理可能干扰了细胞增殖通路（机制推测，有待蛋白水平验证）。
### 局限性
样本量较小（n=5）[S4]，结论需扩大样本验证；未考察剂量-效应关系。
```

## 5. 机器核查（不耗模型请求）
```bash
# Harbor 环境 Skill 位于 /skills/weekly-skill；不存在时退回相对路径
RD=/skills/weekly-skill/scripts/rd_check.py
[ -f "$RD" ] || RD=scripts/rd_check.py
python3 "$RD" /app/work/draft.md /app/work/sources.json /app/work/report.json
```
示意输出（示例，本示例材料下实测）：退出码 0，fail=0，warn=0。
summary 给出 by_kind 与 by_score_dimension（正确性/完整性/可核验性/完成度）计数，
修复前后各跑一次，fail/warn 差值即质量增益证据。
statcheck 演示：若正文误写 `t(28)=2.5, p=0.2`，脚本重算 p≈0.019 并给 statcheck warn。

## 6. 定稿输出（/app/output/）
- `results_discussion.md`：去掉内部标注后的可编辑稿（来源标注移入 result.json 的 sources_map）。
- `result.json`：status=complete，sources_map 逐条列出"正文物 → S#/C# → 材料出处"，
  uncertainty 保留"无参考文献"等缺口，change_log 记录核查前后 fail/warn 计数与修复过程。
