# 最小调用示例（自拟短材料，仅演示接口；输出为示例，非正式案例结果）

## 输入 1：/input/case.json（自拟）
```json
{"case_id": "demo-001",
 "title": "钙钛矿太阳能电池界面稳定性研究",
 "references": ["Zhang et al. (2023) 报道MAPbI3器件在85℃下500小时效率保持率为62%。",
                "Li et al. (2024) 通过界面钝化将保持率提升至78%，但湿热耦合衰减机制不明。"],
 "applicant_preliminary": ["申请人团队已制备SAM空穴传输层器件，初始效率24.1%（已完成）。"]}
```

## 输入 2：/input/task.md（自拟）
"依据给定材料撰写基金申请书的立项依据、研究目标、创新点与研究基础四个章节。"

## 调用方式
```bash
python3 /skills/weekly-skill/scripts/run_grant.py init  --case /input/case.json --task /input/task.md --work /app/work --out /app/output
# （模型按 SKILL.md 第1-2步读台账、写 /app/work/draft.md）
python3 /skills/weekly-skill/scripts/run_grant.py check --work /app/work --out /app/output
python3 /skills/weekly-skill/scripts/run_grant.py pack  --work /app/work --out /app/output --case-id demo-001
```

## 示意输出片段（示例）
- init：3 条证据（S1/S2 文献，P1 申请人前期基础），result.json status=partial。
- 立项依据："已报道 MAPbI3 器件在 85℃ 下 500 小时效率保持率仅 62% [S1]；界面钝化可提升至 78%，但湿热耦合衰减机制仍不明确 [S2]（缺口G1）。申请人已制备初始效率 24.1% 的 SAM 器件[✓][P1]。"
- 研究内容："C1（对应G1，回应缺口G1）：构建湿热老化下界面缺陷演化模型，输出缺陷密度时间关系。"
- 创新点："创新点1（对应C1，对比[S2]）：相比 [S2] 的单一界面钝化，本方案在老化动态维度给出缺陷演化定量模型。"
- check：写"填补国内空白"→报"创新点禁用词：命中 填补空白"；C1 漏写回应缺口→报"孤儿内容"；前期论断未挂[P1]→报"未挂P"。
- 缺团队分工材料：研究基础标"【待补充：团队分工】"并登记 material_gaps。
- 最终 /app/output/：proposal_sections.md、consistency_report.md、route_map.mmd、result.json（含 used_in 与 checks）。
